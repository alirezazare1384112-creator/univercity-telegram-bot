"""Global middleware: every update is matched with a row in ``users``.

Runs in group ``-1`` (before any feature handler) so a user always exists
before a handler touches the database.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.repositories import UserRepository

logger = logging.getLogger(__name__)


async def capture_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create or refresh the user row and expose it through ``user_data``."""
    tg_user = update.effective_user
    if tg_user is None or tg_user.is_bot:
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
    except Exception:
        logger.exception("Could not persist telegram user %s", tg_user.id)
