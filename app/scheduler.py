"""Background scheduler: delivers due reminders and syncs Eitaa channels.

Why a database poller instead of ``JobQueue``:

* pending alerts live in ``reminder_notifications`` -> nothing is lost on
  a restart or a server crash
* no extra dependency (APScheduler) and it is trivial to test
* worst case delay is ``POLL_SECONDS`` (30 s), which is fine for humans
* the same loop imports new Eitaa posts every ``EITAA_SYNC_SECONDS``
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from telegram.ext import Application

from app.config import get_settings
from app.services.eitaa_sync import sync_channels
from app.services.reminder_service import process_due_notifications

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
_TASK_KEY = "reminder_poller_task"


async def run_one_cycle(application: Application) -> dict[str, int]:
    """Send every due reminder once."""
    settings = get_settings()
    return await process_due_notifications(
        application.bot.send_message, settings.timezone
    )


async def run_eitaa_sync() -> int:
    """Import new posts of the configured channels (0 when none configured)."""
    settings = get_settings()
    if not settings.eitaa_sync_urls:
        return 0
    return await sync_channels(settings.eitaa_sync_urls)


async def _poller_loop(application: Application) -> None:
    tick = 0
    while True:
        await asyncio.sleep(POLL_SECONDS)
        tick += 1

        try:
            counters = await run_one_cycle(application)
            if any(counters.values()):
                logger.info("Reminder cycle: %s", counters)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception:
            logger.exception("Reminder cycle failed")

        settings = get_settings()
        sync_every = max(1, settings.eitaa_sync_seconds // POLL_SECONDS)
        if tick % sync_every == 0:
            try:
                imported = await run_eitaa_sync()
                if imported:
                    logger.info("Eitaa sync imported %s post(s)", imported)
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                raise
            except Exception:
                logger.exception("Eitaa sync cycle failed")


async def start_scheduler(application: Application) -> None:
    """Start polling (called by PTB after the bot is initialized)."""
    # send anything that became due while the bot was down
    try:
        counters = await run_one_cycle(application)
        logger.info("Scheduler started (catch-up: %s)", counters)
    except Exception:
        logger.exception("Catch-up reminder cycle failed")

    # pull whatever the channels published while the bot was down
    try:
        imported = await run_eitaa_sync()
        if imported:
            logger.info("Scheduler started (eitaa import: %s)", imported)
    except Exception:
        logger.exception("Initial eitaa sync failed")

    application.bot_data[_TASK_KEY] = asyncio.create_task(_poller_loop(application))


async def stop_scheduler(application: Application) -> None:
    """Stop polling (called by PTB before shutdown)."""
    task: asyncio.Task | None = application.bot_data.pop(_TASK_KEY, None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    logger.info("Scheduler stopped")
