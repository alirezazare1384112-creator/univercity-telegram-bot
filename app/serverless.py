"""Serverless (Vercel) application builder.

Same handlers and API as the long-running bot, but:

- ``updater(None)``: updates arrive via webhook, never long polling.
- no ``post_init`` scheduler: a serverless instance freezes between
  requests, so background loops are useless. Reminders, Eitaa import and
  channel sync are driven by ``POST /api/cron/tick`` instead.
- database-backed persistence so conversations survive cold starts.
"""

from __future__ import annotations

from telegram.ext import Application

from app.bot.handlers import register_handlers
from app.config import get_settings
from app.persistence import DatabasePersistence


def build_serverless_application() -> Application:
    """Create the PTB application wired for Telegram webhooks."""
    settings = get_settings()
    application = (
        Application.builder()
        .token(settings.bot_token)
        .persistence(DatabasePersistence())
        .updater(None)
        .build()
    )
    register_handlers(application)
    return application
