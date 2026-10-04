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

# one chunk per <div class="etme_widget_message_wrap ..."> (i.e. one post)
_CHUNK_RE = re.compile(r'(?=<div class="etme_widget_message_wrap)')
_DATA_POST_RE = re.compile(r'data-post="([^"]+)"')
_TIME_RE = re.compile(r'<time datetime="([^"]+)"')
_TEXT_RE = re.compile(
    r'<div class="etme_widget_message_text js-message_text"[^>]*>(.*?)</div>',
    re.S,
)
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


def parse_posts(page_html: str, *, channel_url: str) -> list[EitaaPost]:
    """Text posts of one channel page; media-only posts are skipped."""
    parsed = urlparse(channel_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    posts: list[EitaaPost] = []
    for chunk in _CHUNK_RE.split(page_html):
        ref_match = _DATA_POST_RE.search(chunk)
        text_match = _TEXT_RE.search(chunk)
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


async def fetch_channel_html(channel_url: str) -> str:
    """GET the public channel page (the only Eitaa interface that exists)."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = await client.get(channel_url)
        response.raise_for_status()
        return response.text


async def import_posts(page_html: str, *, channel_url: str) -> int:
    """Copy every not-yet-known post to each active user; returns rows added."""
    posts = parse_posts(page_html, channel_url=channel_url)
    if not posts:
        return 0

    urls = [post.url for post in posts]
    created = 0
    async with get_session() as session:
        announcements = AnnouncementRepository(session)
        user_ids = await UserRepository(session).list_active_ids()
        for user_id in user_ids:
            existing = await announcements.existing_source_urls(user_id, urls)
            for post in posts:
                if post.url in existing:
                    continue
                await announcements.create(
                    user_id=user_id,
                    title=_title_from(post.text),
                    source=ANNOUNCEMENT_EITAA,
                    text=post.text,
                    source_url=post.url,
                    created_at=post.published_at,
                )
                created += 1
    if created:
        logger.info("Imported %d eitaa post(s) from %s", created, channel_url)
    return created


async def sync_channels(urls: Sequence[str]) -> int:
    """Sync every configured channel; one broken site never stops the rest."""
    total = 0
    for url in urls:
        try:
            page = await fetch_channel_html(url)
            total += await import_posts(page, channel_url=url)
        except Exception:
            logger.exception("Eitaa sync failed for %s", url)
    return total
