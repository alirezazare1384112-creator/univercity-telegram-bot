"""Shared pytest fixtures.

Tests run against an isolated in-memory SQLite database, so they never
touch the development database in ``data/``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import reset_settings_cache
from app.database.database import build_engine
from app.database.models import Base


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
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
