"""Follow user-subscribed channels (Eitaa + public Telegram) and import posts.

Every student adds their own channel links (from the bot menu or the Mini
App). The scheduler fetches each distinct channel once per round, copies
the new text posts into that student's announcements (dedup by
``source_url``, exactly like the global Eitaa sync) and pushes one short
notice per student.

Media-only posts are skipped - resending photos needs an official API
(see README, "needs external API").
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from sqlalchemy import select

from app.database.database import get_session
from app.database.models.user import User
from app.database.models.user_channel import CHANNEL_EITAA, CHANNEL_TELEGRAM
from app.database.repositories import UserChannelRepository
from app.services.eitaa_sync import (
    EitaaPost,
    fetch_channel_html,
    import_for_user,
    parse_posts,
)

logger = logging.getLogger(__name__)

_EITAA_HOSTS = {"eitaa.com", "www.eitaa.com", "eitaa.ir", "www.eitaa.ir"}
_TELEGRAM_HOSTS = {"t.me", "www.t.me", "telegram.me", "telegram.dog"}
# t.me links that are not a public channel username
_TELEGRAM_RESERVED = {"joinchat", "addlist", "addstickers", "addemoji", "share", "proxy", "socks", "login"}
# public Telegram usernames: 5-32 chars of a-z, 0-9 and underscore
_TELEGRAM_HANDLE_RE = re.compile(r"[a-z0-9_]{5,32}")
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def normalize_channel_url(raw: str) -> tuple[str, str, str] | None:
    """``(platform, canonical_url, handle)`` of a channel link, else ``None``.

    Accepts Eitaa links (``eitaa.com/<channel>``, also a single post link)
    and public Telegram links (``t.me/<channel>``, ``t.me/s/<channel>``,
    ``t.me/<channel>/<post id>``); the first path segment is the channel.
    """
    text = (raw or "").strip()
    if not text or len(text) > 255 or text.startswith("@") or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = f"https://{text}"
    try:
        parts = urlparse(text)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    host = parts.netloc.lower()
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return None

    if host in _EITAA_HOSTS:
        handle = segments[0]
        if len(handle) > 128:
            return None
        return CHANNEL_EITAA, f"https://eitaa.com/{handle}", handle

    if host in _TELEGRAM_HOSTS:
        handle = segments[1] if segments[0].lower() == "s" and len(segments) > 1 else segments[0]
        handle = handle.lower()
        if handle in _TELEGRAM_RESERVED or not _TELEGRAM_HANDLE_RE.fullmatch(handle):
            return None
        return CHANNEL_TELEGRAM, f"https://t.me/{handle}", handle

    return None


async def _fetch_html(url: str, *, first_trust_env: bool) -> str:
    """Fetch ``url`` preferring one network mode, then fall back to the other.

    On this network the local Psiphon proxy is flaky while some hosts are
    only reachable through it, so a single failure is not final.
    """
    try:
        return await fetch_channel_html(url, trust_env=first_trust_env)
    except Exception as first_error:  # noqa: BLE001 - any network error triggers the retry
        logger.warning(
            "Fetch (trust_env=%s) failed for %s (%s); retrying the other way",
            first_trust_env, url, type(first_error).__name__,
        )
        return await fetch_channel_html(url, trust_env=not first_trust_env)


async def fetch_posts(platform: str, url: str) -> list[EitaaPost]:
    """Text posts currently visible on the channel's public page."""
    if platform == CHANNEL_TELEGRAM:
        handle = url.rsplit("/", 1)[-1]
        page = await _fetch_html(f"https://t.me/s/{handle}", first_trust_env=True)
        return parse_posts(page, channel_url=url, widget="tgme")
    page = await _fetch_html(url, first_trust_env=False)
    return parse_posts(page, channel_url=url)


async def sync_user_channels() -> dict[int, int]:
    """Import new posts of every subscribed channel.

    Each distinct URL is fetched once (several students may subscribe to
    the same channel). Returns ``{telegram_id: number_of_new_posts}`` so
    the scheduler can push one notice per student.
    """
    async with get_session() as session:
        channels = await UserChannelRepository(session).list_all()
    grouped: dict[str, list[tuple[str, int]]] = {}
    for channel in channels:
        grouped.setdefault(channel.url, []).append((channel.platform, channel.user_id))
    if not grouped:
        return {}

    counts: dict[int, int] = {}
    for url, subscribers in grouped.items():
        platform = subscribers[0][0]
        try:
            posts = await fetch_posts(platform, url)
        except Exception:
            logger.exception("User-channel sync failed for %s", url)
            continue
        if not posts:
            continue
        async with get_session() as session:
            for _platform, user_id in subscribers:
                created = await import_for_user(session, user_id, posts, source=platform)
                if created:
                    counts[user_id] = counts.get(user_id, 0) + created
    if not counts:
        return {}

    async with get_session() as session:
        rows = await session.execute(
            select(User.id, User.telegram_id).where(User.id.in_(list(counts)))
        )
        telegram_ids = dict(rows.all())
    return {
        telegram_ids[user_id]: count
        for user_id, count in counts.items()
        if user_id in telegram_ids
    }


def new_posts_notice(count: int) -> str:
    """Short push text; the full posts live in the announcements inbox."""
    plural = str(count).translate(_FA_DIGITS)
    return (
        f"📢 {plural} اطلاعیه جدید از کانال‌هایی که دنبال می‌کنی رسید.\n"
        "برای دیدن همه، منوی 📢 اطلاعیه‌ها را باز کن."
    )
