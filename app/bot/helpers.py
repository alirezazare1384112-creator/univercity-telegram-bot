"""Small helpers shared by every handler."""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import BaseHandler, ContextTypes, ConversationHandler

from app.config import get_settings

logger = logging.getLogger(__name__)


def open_exclusive(handler: BaseHandler, siblings: list[ConversationHandler]) -> BaseHandler:
    """Wrap ``handler`` so firing it first closes the sibling conversations.

    One feature may own the screen at a time. PTB keeps every conversation's
    state in ``_conversations`` (keyed like ``_get_key``), so a background
    wizard would otherwise swallow the next photo or text - a note's photo
    used to be saved as the weekly schedule.
    """
    original = handler.callback

    async def enter(update: Update, context: ContextTypes.DEFAULT_TYPE):
        for sibling in siblings:
            sibling._conversations.pop(sibling._get_key(update), None)
        return await original(update, context)

    handler.callback = enter
    return handler


def chat_id(update: Any) -> int | None:
    message = update.effective_message
    if message is not None:
        return message.chat_id
    user = update.effective_user
    return user.id if user is not None else None


async def answer(
    update: Any,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None = None,
) -> None:
    """Send a plain text reply.

    Plain text (no Markdown/HTML) is used everywhere on purpose: user input
    is embedded in most messages and bad entities would make Telegram
    reject the message.
    """
    target = chat_id(update)
    if target is None:  # pragma: no cover - defensive
        logger.warning("No chat id available for update %s", getattr(update, "update_id", "?"))
        return
    try:
        await context.bot.send_message(
            chat_id=target,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Failed to send message to chat %s", target)


def is_admin(update: Any) -> bool:
    """Admin access is checked against Telegram id only (see ADMIN_IDS)."""
    user = update.effective_user
    return user is not None and get_settings().is_admin(user.id)


async def current_user_id(update: Any, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Internal ``users.id`` of the sender (cached in ``user_data``)."""
    cached = context.user_data.get("user_id")
    if cached:
        return cached

    tg_user = update.effective_user
    if tg_user is None:
        return None

    from app.database.database import get_session
    from app.database.repositories import UserRepository

    try:
        async with get_session() as session:
            user = await UserRepository(session).get_by_telegram_id(tg_user.id)
    except Exception:
        logger.exception("Could not load user %s", tg_user.id)
        return None

    if user is None:
        return None
    context.user_data["user_id"] = user.id
    return user.id
