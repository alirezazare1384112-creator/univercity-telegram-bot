"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

# Module level singletons, created lazily so tests can override them.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _apply_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """SQLite defaults that every connection of this project needs.

    - foreign_keys=ON   : SQLite ignores FK constraints unless it is set.
    - busy_timeout      : wait instead of failing when the file is locked.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def build_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Create an engine with the right settings for the given driver.

    Used by the application (``get_engine``) and by the tests, so both
    behave identically.
    """
    options: dict[str, Any] = {"echo": False, "future": True}
    options.update(kwargs)

    if url.startswith("sqlite"):
        engine = create_async_engine(url, **options)
        event.listen(engine.sync_engine, "connect", _apply_sqlite_pragmas)
        return engine

    options.setdefault("pool_pre_ping", True)
    options.setdefault("pool_size", 5)
    options.setdefault("max_overflow", 10)
    return create_async_engine(url, **options)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Transactional session scope.

    Commits on success, rolls back on any exception and always closes.
    """
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Close the engine (used on shutdown and between tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


__all__ = [
    "build_engine",
    "dispose_engine",
    "get_engine",
    "get_session",
    "get_session_factory",
]
