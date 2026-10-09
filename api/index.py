"""Vercel serverless entry point.

One FastAPI app that serves the Mini App API plus three bot-side routes:

- ``POST /api/telegram-webhook`` - Telegram pushes updates here.
- ``POST /api/cron/tick``        - external scheduler (cron-job.org) drives
  reminders, Eitaa import and channel sync (serverless has no background loop).
- ``GET  /api/setup``            - one-shot: registers the webhook.

The PTB application is created and initialized lazily on the first request
so the module can be imported at build time without secrets.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, Header, HTTPException, Request  # noqa: E402
from telegram import Update  # noqa: E402

from app.api import create_api  # noqa: E402
from app.config import get_settings  # noqa: E402

logger = logging.getLogger("serverless")

# Paths that must answer even when Telegram/secrets are not configured yet.
_LIGHT_PATHS = {"/api/health", "/api/boot-report"}

_ptb_application = None
_ready = False
_migrated = False


def _get_ptb():
    """Create the webhook-mode PTB application once per instance."""
    global _ptb_application
    if _ptb_application is None:
        from app.serverless import build_serverless_application

        _ptb_application = build_serverless_application()
        api.state.bot_application = _ptb_application
    return _ptb_application


def _run_migrations() -> None:
    """Bring the (Neon) database up to the current schema, once per instance."""
    global _migrated
    if _migrated:
        return
    from alembic import command
    from alembic.config import Config

    # no alembic.ini on the serverless bundle - configure directly
    cfg = Config()
    cfg.set_main_option(
        "script_location", str(BASE_DIR / "app" / "database" / "migrations")
    )
    command.upgrade(cfg, "head")
    _migrated = True
    logger.info("Database migrations applied")


async def _ensure_ready() -> None:
    """Initialize the bot + schema once per cold instance."""
    global _ready
    if _ready:
        return
    try:
        try:
            _run_migrations()
        except Exception:
            logger.exception("Migration attempt failed (will retry on next request)")
        application = _get_ptb()
        await application.initialize()
        _ready = True
        logger.info("Serverless bot initialized")
    except Exception as exc:
        logger.exception("Serverless init failed")
        raise HTTPException(status_code=503, detail="bot initializing, retry") from exc


def _require_bearer(authorization: str | None) -> None:
    secret = os.getenv("CRON_SECRET", "")
    if not secret or authorization != f"Bearer {secret}":
        raise HTTPException(status_code=403, detail="forbidden")


api: FastAPI = create_api(None)


@api.middleware("http")
async def _serverless_lifecycle(request: Request, call_next):
    """Initialize the bot before any real /api/* request is served."""
    if request.url.path.startswith("/api/") and request.url.path not in _LIGHT_PATHS:
        await _ensure_ready()
    return await call_next(request)


@api.post("/api/telegram-webhook")
@api.post("/api/index/telegram-webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret or x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="forbidden")
    application = _get_ptb()
    payload = await request.json()
    update = Update.de_json(payload, application.bot)
    if update is not None:
        await application.process_update(update)
        await application.update_persistence()
        # opportunistic sweeps: an active bot keeps its reminders fresh even
        # when no external cron is configured yet (throttled per instance)
        await _maybe_background_sweeps(application)
    return {"ok": True}


async def _run_sweeps(application, *, with_sync: bool) -> dict[str, object]:
    """Reminder sweep (+ optional channel syncs). Never raises."""
    from app.scheduler import run_eitaa_sync, run_one_cycle, run_user_channel_sync

    results: dict[str, object] = {}
    try:
        results["reminders"] = await run_one_cycle(application)
    except Exception:
        logger.exception("sweep: reminder cycle failed")
        results["reminders"] = "failed"

    if with_sync:
        try:
            imported = await run_eitaa_sync()
            if imported:
                logger.info("sweep: eitaa imported %s post(s)", imported)
            results["eitaa"] = imported
        except Exception:
            logger.exception("sweep: eitaa sync failed")

        try:
            notified = await run_user_channel_sync(application)
            if notified:
                logger.info("sweep: user channels notified %s", notified)
            results["user_channels"] = {str(k): v for k, v in notified.items()}
        except Exception:
            logger.exception("sweep: user channel sync failed")
    return results


# instance-local throttle for the webhook piggyback (seconds)
_LAST_REMINDER_SWEEP = 0.0
_LAST_SYNC_SWEEP = 0.0
_REMINDER_SWEEP_SECONDS = 60.0
_SYNC_SWEEP_SECONDS = 300.0


async def _maybe_background_sweeps(application) -> None:
    """Run reminder/sync sweeps piggybacked on real user traffic."""
    global _LAST_REMINDER_SWEEP, _LAST_SYNC_SWEEP

    import time as _time

    now = _time.monotonic()
    need_reminders = now - _LAST_REMINDER_SWEEP >= _REMINDER_SWEEP_SECONDS
    need_sync = now - _LAST_SYNC_SWEEP >= _SYNC_SWEEP_SECONDS
    if not (need_reminders or need_sync):
        return
    if need_reminders:
        _LAST_REMINDER_SWEEP = now
    if need_sync:
        _LAST_SYNC_SWEEP = now
    await _run_sweeps(application, with_sync=need_sync)


@api.post("/api/cron/tick")
@api.post("/api/index/cron/tick")
async def cron_tick(authorization: str | None = Header(default=None)) -> dict:
    _require_bearer(authorization)
    application = _get_ptb()
    results: dict[str, object] = {}

    # re-assert the webhook on every tick (heals an accidentally deleted hook)
    settings = get_settings()
    webhook_url = f"{settings.webapp_url}/api/telegram-webhook"
    try:
        await application.bot.set_webhook(
            url=webhook_url,
            secret_token=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        )
        results["webhook"] = webhook_url
    except Exception:
        logger.exception("set_webhook from cron failed")

    results.update(await _run_sweeps(application, with_sync=True))
    await application.update_persistence()
    return results


@api.get("/api/setup")
@api.get("/api/index/setup")
async def setup(key: str = "") -> dict[str, str]:
    secret = os.getenv("CRON_SECRET", "")
    if not secret or key != secret:
        raise HTTPException(status_code=403, detail="forbidden")
    application = _get_ptb()
    settings = get_settings()
    webhook_url = f"{settings.webapp_url}/api/telegram-webhook"
    await application.bot.set_webhook(
        url=webhook_url,
        secret_token=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        drop_pending_updates=True,
    )
    await application.bot.set_my_commands(
        [
            ("start", "منوی اصلی"),
            ("menu", "منو"),
            ("help", "راهنما"),
        ]
    )
    logger.info("Webhook registered: %s", webhook_url)
    return {"webhook": webhook_url, "status": "registered"}


# Vercel looks for a module-level ASGI callable named ``app``.
app = api
