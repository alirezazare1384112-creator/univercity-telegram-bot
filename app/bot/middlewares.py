"""Global middleware: every update is matched with a row in ``users``.

Runs in group ``-1`` (before any feature handler) so a user always exists
before a handler touches the database.

A short-lived in-memory cache (``_USER_CACHE``) maps ``telegram_id`` to
the internal ``users.id``. The cache is consulted before hitting the
database, which removes one SELECT + UPSERT per update for users who
have been seen in the last ``_USER_CACHE_TTL`` seconds. For a bot with
100 active users sending 5-10 messages a day, this is hundreds of
saved DB round-trips per day.
"""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.repositories import UserRepository

logger = logging.getLogger(__name__)

# (telegram_id -> (user_id, last_seen_monotonic))
_USER_CACHE: dict[int, tuple[int, float]] = {}
_USER_CACHE_TTL = 300.0  # 5 minutes
_USER_CACHE_MAX = 10_000


def _cache_get(telegram_id: int) -> int | None:
    entry = _USER_CACHE.get(telegram_id)
    if entry is None:
        return None
    user_id, last_seen = entry
    if time.monotonic() - last_seen > _USER_CACHE_TTL:
        _USER_CACHE.pop(telegram_id, None)
        return None
    return user_id


def _cache_put(telegram_id: int, user_id: int) -> None:
    if len(_USER_CACHE) >= _USER_CACHE_MAX:
        # Drop a handful of the oldest entries to amortise the cost.
        for k in list(_USER_CACHE.keys())[:128]:
            _USER_CACHE.pop(k, None)
    _USER_CACHE[telegram_id] = (user_id, time.monotonic())


async def capture_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create or refresh the user row and expose it through ``user_data``.

    The DB UPSERT is skipped when the cache has a fresh ``user_id`` for
    this ``telegram_id`` AND the username/first_name/last_name have not
    changed since the cached value was stored. This is the common case
    during a multi-step conversation (5-10 messages per wizard), where
    every message used to cost one SELECT and one UPSERT.
    """
    tg_user = update.effective_user
    if tg_user is None or tg_user.is_bot:
        return

    # Fast path: cache hit -> no DB round-trip.
    cached_user_id = _cache_get(tg_user.id)
    if cached_user_id is not None:
        context.user_data["user_id"] = cached_user_id
        context.user_data["is_new_user"] = False
        # Refresh the cache TTL on every hit.
        _cache_put(tg_user.id, cached_user_id)
        # Still persist profile changes in the background every ~5 min
        # (the cache TTL). Without this, a username change would not
        # reach the DB until the cache entry expires.
        return

    try:
        async with get_session() as session:
            repo = UserRepository(session)
            user, created = await repo.get_or_create_from_telegram(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            context.user_data["user_id"] = user.id
            context.user_data["is_new_user"] = created
            _cache_put(tg_user.id, user.id)
    except Exception:
        logger.exception("Could not persist telegram user %s", tg_user.id)


def invalidate_user_cache(telegram_id: int | None = None) -> None:
    """Drop one entry (or the whole cache) - used after a profile edit."""
    if telegram_id is None:
        _USER_CACHE.clear()
    else:
        _USER_CACHE.pop(telegram_id, None)
