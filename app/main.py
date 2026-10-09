"""Application bootstrap: build the Telegram application and run it."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from telegram.ext import Application

from app.bot.handlers import register_handlers
from app.config import Settings, get_settings
from app.database.database import dispose_engine, get_session
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

PLACEHOLDER_TOKEN_PREFIX = "000000000"
# grace period for a boot that is about to finish (tests, quick Ctrl+C);
# a bot stuck behind a dead network is cancelled after this
_BOOT_GRACE_SECONDS = 5.0
# one full boot attempt (initialize + start_polling + start + scheduler)
# may not hang longer than this (blocked DNS, blackholed route); the retry
# loop logs and starts a fresh attempt
_BOOT_ATTEMPT_SECONDS = 60.0


async def _post_init(application: Application) -> None:
    """Start background jobs once the bot is ready."""
    from app.scheduler import start_scheduler

    await start_scheduler(application)


async def _post_shutdown(application: Application) -> None:
    """Stop background jobs and close the database engine."""
    from app.scheduler import stop_scheduler

    await stop_scheduler(application)
    await dispose_engine()


def build_application() -> Application:
    """Create the PTB application and register every handler.

    ``concurrent_updates=True`` lets PTB process multiple updates in
    parallel. The default (False) serialises every update through one
    queue, so a single slow handler (e.g. a file upload) blocks every
    other user. With concurrency enabled the bot keeps responding even
    while one user is in the middle of a multi-step wizard.
    """
    settings = get_settings()
    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .concurrent_updates(True)
        .build()
    )
    register_handlers(app)
    return app


def _validate_token(settings: Settings) -> None:
    if not settings.bot_token:
        raise SystemExit(
            "BOT_TOKEN is empty.\n"
            "Copy .env.example to .env and set BOT_TOKEN (ask @BotFather)."
        )
    if settings.bot_token.startswith(PLACEHOLDER_TOKEN_PREFIX):
        raise SystemExit(
            "BOT_TOKEN still contains the placeholder value from .env.example.\n"
            "Put the real token issued by @BotFather into .env"
        )


async def check_database() -> dict[str, str]:
    """Verify that the database is reachable (used by ``run.py --check``)."""
    from sqlalchemy import text

    info: dict[str, str] = {}
    async with get_session() as session:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
        info["connection"] = "ok"

        rows = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if get_settings().database_url.startswith("sqlite")
            else text(
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        )
        tables = [row[0] for row in rows]
        info["tables"] = ", ".join(tables) if tables else "(none)"

        try:
            version = await session.execute(text("SELECT version_num FROM alembic_version"))
            info["alembic"] = str(version.scalar_one())
        except Exception:  # noqa: BLE001 - informational only
            info["alembic"] = "not applied yet (run: alembic upgrade head)"
    return info


async def healthcheck() -> int:
    """Run all local checks that do not need a real Telegram token."""
    settings = get_settings()
    print("== Student Assistant Bot - environment check ==")
    print(f"database_url : {settings.database_url}")
    print(f"timezone     : {settings.timezone}")
    print(f"gpa_url      : {settings.gpa_calculator_url or '(empty)'}")
    print(f"admin_ids    : {sorted(settings.admin_ids) or '(empty)'}")
    print(
        "eitaa_sync   : "
        + (", ".join(settings.eitaa_sync_urls) or "(disabled)")
        + f" (every {settings.eitaa_sync_seconds}s)"
    )
    print(
        "bot_token    : "
        + (
            "set (not checked - needs a real token)"
            if settings.bot_token and not settings.bot_token.startswith(PLACEHOLDER_TOKEN_PREFIX)
            else "missing / placeholder"
        )
    )
    try:
        info = await check_database()
    except Exception as exc:  # noqa: BLE001
        print(f"database     : FAILED -> {exc}")
        return 1
    print(f"database     : {info['connection']}")
    print(f"tables       : {info['tables']}")
    print(f"alembic      : {info['alembic']}")
    print("== check finished ==")
    return 0


def run_bot() -> None:
    """Start long polling only (bot without the Mini App API)."""
    settings = get_settings()
    setup_logging(settings)
    _validate_token(settings)

    logger.info("Starting Student Assistant Bot (timezone=%s)", settings.timezone)
    app = build_application()
    app.run_polling(
        allowed_updates=None,
        drop_pending_updates=True,
        close_loop=False,
    )


async def _boot_bot_once(application: Application, state: dict[str, bool]) -> None:
    """One full boot attempt: initialize, start polling, start, scheduler."""
    await application.initialize()
    # a cancelled previous attempt may have left the updater mid-flight
    with contextlib.suppress(Exception):
        await application.updater.stop()
    await application.updater.start_polling(drop_pending_updates=True)
    state["polling_started"] = True
    await application.start()
    state["app_started"] = True
    # PTB only runs post_init inside run_polling(); _serve() drives the
    # lifecycle manually, so the scheduler must be started here explicitly.
    try:
        await _post_init(application)
    except Exception:
        logger.exception("Post-init (scheduler) failed; the bot stays up")


async def _boot_forever(application: Application, state: dict[str, bool]) -> None:
    """Endless boot retries for the Telegram side (API is already up).

    A blackholed network can hang ``initialize()`` *or* ``start_polling``
    (long TCP timeouts that swallow cancellation), so every attempt runs
    as its own task with a hard time cap: a stuck attempt is abandoned,
    cleaned up, and retried with backoff.
    """
    delay = 5.0
    attempt = 0
    while True:
        attempt += 1
        task = asyncio.create_task(_boot_bot_once(application, state))
        done, _ = await asyncio.wait({task}, timeout=_BOOT_ATTEMPT_SECONDS)
        if done:
            error = task.exception()
            if error is None:
                return
        else:
            task.cancel()
            task.add_done_callback(_eat_task_exception)
            error = TimeoutError(f"boot attempt hung for {_BOOT_ATTEMPT_SECONDS}s")
            with contextlib.suppress(Exception):
                await application.updater.stop()
            with contextlib.suppress(Exception):
                await application.shutdown()
            with contextlib.suppress(Exception):
                await application.stop()
        logger.warning(
            "Bot boot failed (attempt %s): %s — retrying in %.0fs",
            attempt,
            error,
            delay,
        )
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60.0)


def _log_boot_failure(task: asyncio.Task) -> None:
    """Surface a dead/hung boot task immediately, not only at shutdown."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("Bot boot failed", exc_info=error)


def _eat_task_exception(task: asyncio.Task) -> None:
    """Retrieve the exception of an abandoned attempt (avoids warnings)."""
    if not task.cancelled():
        task.exception()


async def _serve(settings: Settings) -> None:
    """Run PTB long polling and the FastAPI server in one event loop.

    The API boots first and stays up even when Telegram is unreachable;
    the bot boots in the background (``_boot_forever``), so a
    network outage can no longer take the Mini App down with it.

    Uvicorn tuning:
    - ``timeout_keep_alive=5``: close idle keep-alive connections after
      5 s (default 5 is fine, but explicit so we don't regress). Frees
      file descriptors faster under load.
    - ``limit_concurrency`` and ``backlog`` are left at Uvicorn defaults;
      the FastAPI rate limiter is the real cap.
    """
    import uvicorn

    from app.api import create_api

    logger.info(
        "Starting bot + Mini App API on http://%s:%s",
        settings.api_host,
        settings.api_port,
    )
    application = build_application()
    state: dict[str, bool] = {}

    server = uvicorn.Server(
        uvicorn.Config(
            create_api(application),
            host=settings.api_host,
            port=settings.api_port,
            log_level=settings.log_level.lower(),
            timeout_keep_alive=5,
            # Cap the in-flight request count so a flood of Mini App
            # polls cannot exhaust memory. Default is None (unlimited).
            limit_concurrency=200,
            # OS-level listen backlog; raised from the default 101 so
            # connection spikes during a broadcast don't drop clients.
            backlog=2048,
        )
    )
    bot_task = asyncio.create_task(_boot_forever(application, state))
    bot_task.add_done_callback(_log_boot_failure)
    try:
        await server.serve()
    finally:
        # give a boot that is about to finish a moment to complete
        await asyncio.wait({bot_task}, timeout=_BOOT_GRACE_SECONDS)
        if not bot_task.done():
            bot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bot_task
        if state.get("polling_started"):
            with contextlib.suppress(Exception):
                await application.updater.stop()
        if state.get("app_started"):
            with contextlib.suppress(Exception):
                await application.stop()
            with contextlib.suppress(Exception):
                await _post_shutdown(application)
            with contextlib.suppress(Exception):
                await application.shutdown()


def run_services() -> None:
    """Production entry point: Telegram bot + Mini App API together."""
    settings = get_settings()
    setup_logging(settings)
    _validate_token(settings)
    asyncio.run(_serve(settings))


if __name__ == "__main__":  # pragma: no cover
    run_bot()
