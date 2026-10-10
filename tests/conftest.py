"""Shared pytest fixtures.

Tests run against an isolated in-memory SQLite database, so they never
touch the development database in ``data/``.
"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings, reset_settings_cache
from app.database.database import build_engine
from app.database.models import Base


def sign_init_data(fields: dict[str, str], *, bot_token: str | None = None) -> str:
    """Build a valid Telegram initData query string for tests."""
    token = get_settings().bot_token if bot_token is None else bot_token
    pairs = sorted(fields.items())
    data_check_string = "\n".join(f"{key}={value}" for key, value in pairs)
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode([*pairs, ("hash", signature)])


@pytest_asyncio.fixture
async def engine():
    engine = build_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as db_session:
        yield db_session
        await db_session.rollback()


@pytest_asyncio.fixture
async def db(engine, session_factory):
    """Point the application at the in-memory test database.

    Handlers always open sessions through ``app.database.database``,
    so the module globals are swapped for the duration of one test.
    """
    import app.database.database as db_module

    previous_engine = db_module._engine
    previous_factory = db_module._session_factory
    db_module._engine = engine
    db_module._session_factory = session_factory
    try:
        yield session_factory
    finally:
        db_module._engine = previous_engine
        db_module._session_factory = previous_factory


@pytest.fixture(autouse=True)
def no_real_telegram_calls(monkeypatch):
    """Keep every test offline: any Telegram API call on a constructed
    object (callback answers, edits, ...) becomes a no-op."""
    import telegram

    async def _noop(*_args, **_kwargs):
        return True

    for name in ("answer", "edit_message_text", "edit_message_reply_markup", "delete"):
        if hasattr(telegram.CallbackQuery, name):
            monkeypatch.setattr(telegram.CallbackQuery, name, _noop, raising=True)


@pytest.fixture(autouse=True)
def deterministic_settings(monkeypatch):
    """Pin every setting a test may read.

    CI runs without a ``.env`` file, so anything read from the environment
    (GPA url, admin ids, sync channels, timezone, database url) must have
    the same value on every machine.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/bot.db")
    monkeypatch.setenv("GPA_CALCULATOR_URL", "https://example.com/gpa")
    monkeypatch.setenv("ADMIN_IDS", "")
    monkeypatch.setenv("EITAA_SYNC_URLS", "")
    monkeypatch.setenv("EITAA_SYNC_SECONDS", "300")
    monkeypatch.setenv("TIMEZONE", "Asia/Tehran")
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST-TOKEN")
    monkeypatch.setenv("WEBAPP_URL", "")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "8000")
    monkeypatch.setenv("WEBAPP_AUTH_MAX_AGE", "86400")
    # Disable auto-provisioned default reminders in tests so the reminder
    # API tests see an empty list on first login. The default-reminder
    # feature has its own dedicated tests.
    monkeypatch.setenv("DEFAULT_REMINDERS_ENABLED", "false")
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture(autouse=True)
def clear_telegram_file_cache(tmp_path):
    """Downloads are cached in memory and on disk; reset both per test."""
    from app.api import files as files_module
    from app.api.files import clear_file_cache

    clear_file_cache()
    files_module.set_disk_cache_dir(tmp_path / "telegram_files")


@pytest.fixture(autouse=True)
def clear_user_middleware_cache():
    """The user-middleware cache (``_USER_CACHE``) survives across tests
    and would make ``capture_user`` skip the DB on the second test that
    uses the same ``telegram_id``, breaking every test that swaps the
    in-memory DB. Reset it before each test."""
    from app.bot.middlewares import invalidate_user_cache

    invalidate_user_cache()
    yield
    invalidate_user_cache()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def api_client(db):
    """httpx client wired to the Mini App API (test database via ``db``)."""
    import httpx

    from app.api import create_api

    transport = httpx.ASGITransport(app=create_api(None))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
