"""Background scheduler: delivers due reminders, syncs Eitaa channels and
imports posts of user-subscribed channels.

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
from pathlib import Path

from sqlalchemy import select, text
from telegram.ext import Application

from app.bot.keyboards.main_menu import main_menu_keyboard
from app.config import get_settings
from app.database.database import get_session
from app.database.models.user import User
from app.services.channel_sync import new_posts_notice, sync_user_channels
from app.services.eitaa_sync import close_shared_client, sync_channels
from app.services.reminder_service import process_due_notifications

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
# Cap broadcast concurrency so a 500-user menu refresh does not trip
# Telegram's ~30 msg/s rate limit. 10 simultaneous sends + the natural
# per-request latency keeps us well under the limit.
_BROADCAST_CONCURRENCY = 10
_TASK_KEY = "reminder_poller_task"
# last WEBAPP_URL delivered to users (quick tunnels rotate the address)
_WEBAPP_URL_MARKER = Path("data/webapp_url")
# serverless shares nothing but Neon, so the marker row lives there
_MARKER_DDL = """
CREATE TABLE IF NOT EXISTS persistence_store (
    kind TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (kind, entry_key)
)
"""


async def run_one_cycle(application: Application) -> dict[str, int]:
    """Send every due reminder once."""
    settings = get_settings()
    return await process_due_notifications(
        application.bot.send_message, settings.timezone
    )


async def run_webapp_url_notice(
    application: Application, marker: Path | None = None, *, force: bool = False
) -> bool:
    """Push a fresh main menu when the Mini App address changed.

    ``web_app`` buttons embed their URL at send time and never ping the
    bot, so after a tunnel rotation users keep tapping a dead link until
    something re-renders their keyboard. Compares ``WEBAPP_URL`` with the
    last address we delivered and, when it differs, sends every user the
    menu again - one message per rotation.

    ``force=True`` re-sends even when the address did not change: clients
    keep the last reply keyboard until a new one arrives, so this heals a
    stale keyboard left over from an older deploy.

    Sends run concurrently (cap 10) so a 500-user rotation finishes in
    ~50 seconds instead of ~500 seconds.
    """
    url = get_settings().webapp_url
    if not url.startswith("https://"):
        return False
    last = await _read_marker(marker)
    if last == url and not force:
        return False
    async with get_session() as session:
        telegram_ids = [
            row[0] for row in (await session.execute(select(User.telegram_id))).all()
        ]
    text_msg = (
        "📱 منوی جدید ربات 👇\n"
        "برای باز کردن مینی‌اپ روی دکمهٔ «📱 باز کردن مینی‌اپ» بزن تا ربات "
        "دکمهٔ باز کردن را بفرستد."
    )
    markup = main_menu_keyboard()
    sent = 0
    sent_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(_BROADCAST_CONCURRENCY)

    async def _send_one(telegram_id: int) -> None:
        nonlocal sent
        async with semaphore:
            try:
                await application.bot.send_message(
                    chat_id=telegram_id, text=text_msg, reply_markup=markup
                )
                async with sent_lock:
                    sent += 1
            except Exception:
                logger.exception("Could not send the webapp link update to %s", telegram_id)

    await asyncio.gather(*(_send_one(tid) for tid in telegram_ids))

    await _write_marker(marker, url)
    logger.info("Webapp url notice sent to %s user(s)", sent)
    return True


def _webapp_url_marker_path() -> Path:
    """Marker path: the repo's ``data/`` folder when running locally."""
    return _WEBAPP_URL_MARKER


async def _read_marker(marker: Path | None) -> str:
    """Last Mini App URL we delivered; empty when we have not sent one yet.

    Serverless keeps this in Neon: each instance gets a fresh filesystem, so
    a local file would look "unread" again on every cold start and re-send the
    menu to every user. Passing ``marker`` still forces the local file path,
    which is what tests and a local run use.
    """
    if marker is None:
        try:
            async with get_session() as session:
                await session.execute(text(_MARKER_DDL))
                row = (
                    await session.execute(
                        text(
                            "SELECT value FROM persistence_store "
                            "WHERE kind = 'webapp_url' AND entry_key = 'notice'"
                        )
                    )
                ).first()
                return str(row[0]) if row and row[0] else ""
        except Exception:
            logger.exception("Could not read the webapp url marker from the database")
            return ""
    try:
        return marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    except OSError:
        logger.exception("Could not read the webapp url marker")
        return ""


async def _write_marker(marker: Path | None, url: str) -> None:
    """Remember the URL we just delivered so the next run does not repeat it."""
    if marker is None:
        try:
            async with get_session() as session:
                await session.execute(text(_MARKER_DDL))
                await session.execute(
                    text(
                        "INSERT INTO persistence_store (kind, entry_key, value) "
                        "VALUES ('webapp_url', 'notice', :value) "
                        "ON CONFLICT (kind, entry_key) DO UPDATE SET value = :value"
                    ),
                    {"value": url},
                )
                await session.commit()
            return
        except Exception:
            logger.exception("Could not persist the webapp url marker")
            return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(url, encoding="utf-8")
    except OSError:
        logger.exception("Could not remember the webapp url locally")


async def run_eitaa_sync() -> int:
    """Import new posts of the configured channels (0 when none configured)."""
    settings = get_settings()
    if not settings.eitaa_sync_urls:
        return 0
    return await sync_channels(settings.eitaa_sync_urls)


async def run_user_channel_sync(application: Application) -> dict[int, int]:
    """Import posts of user-subscribed channels and push one notice each."""
    counts = await sync_user_channels()
    for telegram_id, count in counts.items():
        try:
            await application.bot.send_message(
                chat_id=telegram_id, text=new_posts_notice(count)
            )
        except Exception:
            logger.exception("Could not notify %s about %s new post(s)", telegram_id, count)
    return counts


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

            try:
                notified = await run_user_channel_sync(application)
                if notified:
                    logger.info("User-channel sync notified %s", notified)
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                raise
            except Exception:
                logger.exception("User-channel sync cycle failed")


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

    # same for the channels each student subscribed to individually
    try:
        notified = await run_user_channel_sync(application)
        if notified:
            logger.info("Scheduler started (user channels: %s)", notified)
    except Exception:
        logger.exception("Initial user-channel sync failed")

    # if the tunnel gave the Mini App a new address, refresh every menu
    try:
        await run_webapp_url_notice(application)
    except Exception:
        logger.exception("Webapp url notice failed")

    application.bot_data[_TASK_KEY] = asyncio.create_task(_poller_loop(application))


async def stop_scheduler(application: Application) -> None:
    """Stop polling (called by PTB before shutdown)."""
    task: asyncio.Task | None = application.bot_data.pop(_TASK_KEY, None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    # Close the shared HTTP client so the process can exit cleanly.
    with contextlib.suppress(Exception):
        await close_shared_client()
    logger.info("Scheduler stopped")
