"""Application bootstrap: build the Telegram application and run it."""

from __future__ import annotations

import logging

from telegram.ext import Application

from app.bot.handlers import register_handlers
from app.config import Settings, get_settings
from app.database.database import dispose_engine, get_session
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

PLACEHOLDER_TOKEN_PREFIX = "000000000"


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
    """Create the PTB application and register every handler."""
    settings = get_settings()
    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
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
    """Start long polling (production entry point)."""
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


if __name__ == "__main__":  # pragma: no cover
    run_bot()
