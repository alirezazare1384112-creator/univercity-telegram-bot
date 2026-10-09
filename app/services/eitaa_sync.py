"""Import announcements from the public web page of Eitaa channels.

Eitaa has no bot API (developer.eitaa.com only ships a web mini-app), so
the bot reads the public channel page instead, every few minutes (see
``EITAA_SYNC_SECONDS`` in ``.env``). Each text post is copied to every
active user; the permalink ``https://eitaa.com/<channel>/<post id>`` is
stored in ``source_url`` and doubles as the dedup key.

Media-only posts are skipped for now: re-sending photos/videos would
require an official API (see README, "needs external API").
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.database.database import get_session
from app.database.models.announcement import (
    ANNOUNCEMENT_EITAA,
    MAX_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
)
from app.database.repositories import AnnouncementRepository, UserRepository

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Reusable process-wide HTTP client. Building a new ``httpx.AsyncClient``
# per request burns a full TCP+TLS handshake (200-800 ms on a flaky
# network), which is the dominant cost of the Eitaa sync loop. The
# client is created lazily on first use and closed on engine shutdown.
# Limits match the use case: at most a handful of channel URLs are
# fetched per sync round, so 10 connections is plenty; keepalive makes
# the second sync round ~3-5x faster.
_shared_client: httpx.AsyncClient | None = None
_shared_client_lock = asyncio.Lock()


async def get_shared_client() -> httpx.AsyncClient:
    """Return the process-wide ``httpx.AsyncClient`` (created lazily)."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        return _shared_client
    async with _shared_client_lock:
        if _shared_client is None or _shared_client.is_closed:
            _shared_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": _USER_AGENT},
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=120.0,
                ),
            )
    return _shared_client


async def close_shared_client() -> None:
    """Close the shared client (called on application shutdown)."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None

# one chunk per message wrapper div (i.e. one post); the class prefix differs
# per site - Eitaa uses ``etme_widget_message_*`` (a Telegram clone) and
# Telegram's public ``/s/`` preview uses ``tgme_widget_message_*``
_DATA_POST_RE = re.compile(r'data-post="([^"]+)"')
_TIME_RE = re.compile(r'<time datetime="([^"]+)"')
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TITLE_FALLBACK = "اطلاعیه"


@dataclass(frozen=True, slots=True)
class EitaaPost:
    """One imported post of the channel page."""

    url: str
    text: str
    published_at: datetime | None


def _clean_text(raw_html: str) -> str:
    """Visible text of a message body (tags out, ``<br>`` becomes a line)."""
    text = _BR_RE.sub("\n", raw_html)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    lines = [line.rstrip() for line in text.splitlines()]
    return _BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()


def _title_from(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:MAX_TITLE_LENGTH]
    return _TITLE_FALLBACK


def _published_at(raw: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Ignoring bad eitaa timestamp: %r", raw)
        return None
    # database datetimes are naive UTC (see TimestampMixin)
    return moment.astimezone(UTC).replace(tzinfo=None)


def parse_posts(
    page_html: str, *, channel_url: str, widget: str = "etme"
) -> list[EitaaPost]:
    """Text posts of one channel page; media-only posts are skipped.

    ``widget`` is the CSS class prefix of the site markup: ``etme`` for
    Eitaa, ``tgme`` for Telegram's public channel preview.
    """
    parsed = urlparse(channel_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    chunk_re = re.compile(f'(?=<div class="{widget}_widget_message_wrap)')
    text_re = re.compile(
        rf'<div class="{widget}_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        re.S,
    )
    posts: list[EitaaPost] = []
    for chunk in chunk_re.split(page_html):
        ref_match = _DATA_POST_RE.search(chunk)
        text_match = text_re.search(chunk)
        if ref_match is None or text_match is None:
            continue
        text = _clean_text(text_match.group(1))
        if not text:
            continue
        time_match = _TIME_RE.search(chunk)
        published_at = _published_at(time_match.group(1)) if time_match else None
        posts.append(
            EitaaPost(
                url=f"{origin}/{ref_match.group(1)}",
                text=text[:MAX_TEXT_LENGTH],
                published_at=published_at,
            )
        )
    return posts


async def fetch_channel_html(channel_url: str, *, trust_env: bool = False) -> str:
    """GET the public channel page (the only Eitaa interface that exists).

    ``trust_env`` opts into the process-wide HTTP proxy: public ``t.me``
    previews need it on networks where Telegram is blocked, while Eitaa
    pages are fetched directly.

    The request reuses the process-wide ``httpx.AsyncClient`` when the
    proxy is not needed: the second and later sync rounds reuse the
    warm keepalive connection and skip the TCP+TLS handshake (saves
    200-800 ms per channel on a typical Iranian mobile network).
    """
    if not trust_env:
        client = await get_shared_client()
        response = await client.get(channel_url)
        response.raise_for_status()
        return response.text

    # Proxy mode: build a one-off client (the shared client has no proxy).
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": _USER_AGENT},
        trust_env=trust_env,
    ) as client:
        response = await client.get(channel_url)
        response.raise_for_status()
        return response.text


async def import_for_user(
    session, user_id: int, posts: Sequence[EitaaPost], *, source: str
) -> int:
    """Copy the posts the user does not have yet; returns rows added.

    The dedup SELECT runs once per (user, channel-page) pair and the new
    rows are flushed once at the end, so importing 20 posts costs 2 DB
    round-trips instead of 20.
    """
    announcements = AnnouncementRepository(session)
    urls = [post.url for post in posts]
    existing = await announcements.existing_source_urls(user_id, urls)
    created = 0
    for post in posts:
        if post.url in existing:
            continue
        await announcements.create(
            user_id=user_id,
            title=_title_from(post.text),
            source=source,
            text=post.text,
            source_url=post.url,
            created_at=post.published_at,
        )
        created += 1
    if created:
        await session.flush()
    return created


async def import_posts(page_html: str, *, channel_url: str) -> int:
    """Copy every not-yet-known post to each active user; returns rows added."""
    posts = parse_posts(page_html, channel_url=channel_url)
    if not posts:
        return 0

    created = 0
    async with get_session() as session:
        user_ids = await UserRepository(session).list_active_ids()
        for user_id in user_ids:
            created += await import_for_user(
                session, user_id, posts, source=ANNOUNCEMENT_EITAA
            )
    if created:
        logger.info("Imported %d eitaa post(s) from %s", created, channel_url)
    return created


async def sync_channels(urls: Sequence[str]) -> int:
    """Sync every configured channel; one broken site never stops the rest.

    Channels are fetched concurrently (capped at 5 simultaneous requests)
    so a sync round of N channels finishes in ``max(latencies)`` instead
    of ``sum(latencies)``. Typical win: 5 channels × 600 ms = 600 ms
    instead of 3000 ms.
    """
    if not urls:
        return 0
    semaphore = asyncio.Semaphore(5)

    async def _one(url: str) -> int:
        async with semaphore:
            try:
                page = await fetch_channel_html(url)
                return await import_posts(page, channel_url=url)
            except Exception:
                logger.exception("Eitaa sync failed for %s", url)
                return 0

    results = await asyncio.gather(*(_one(u) for u in urls))
    return sum(results)
