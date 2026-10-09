"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import os
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

    - ``foreign_keys=ON`` : SQLite ignores FK constraints unless it is set.
    - ``busy_timeout``    : wait (up to 10 s) instead of failing when the file
                            is locked. 10 s matches the highest realistic
                            write batch in this project (broadcast / import).
    - ``journal_mode=WAL``: readers never block the writer, so the scheduler
                            loop and the request handlers can run at the same
                            time on a single SQLite file. This is the single
                            biggest SQLite scalability knob.
    - ``synchronous=NORMAL``: safe with WAL and ~2-5x faster than FULL.
    - ``cache_size=-65536``: 64 MB in-memory page cache (negative = KiB).
    - ``temp_store=MEMORY``: temp tables/indexes live in RAM, not on disk.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-65536")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()


def _pool_kwargs_from_env() -> dict[str, Any]:
    """Read the optional DB_POOL_* env vars (PostgreSQL only).

    Defaults are sized for a small single-instance deployment (~100 active
    users). The values scale linearly with concurrency: a 4-worker deployment
    should keep the sum of all ``pool_size + max_overflow`` below the
    PostgreSQL ``max_connections`` setting (default 100).
    """
    def _read_int(name: str, default: int, *, minimum: int = 1) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return max(minimum, int(raw))
        except ValueError:
            return default

    return {
        "pool_size": _read_int("DB_POOL_SIZE", 20),
        "max_overflow": _read_int("DB_MAX_OVERFLOW", 30),
        "pool_timeout": _read_int("DB_POOL_TIMEOUT", 30),
        "pool_recycle": _read_int("DB_POOL_RECYCLE", 1800, minimum=60),
    }


def build_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Create an engine with the right settings for the given driver.

    Used by the application (``get_engine``) and by the tests, so both
    behave identically.
    """
    options: dict[str, Any] = {"echo": False, "future": True}
    options.update(kwargs)

    if url.startswith("sqlite"):
        # SQLite: ``check_same_thread`` must be False so async workers
        # (uvicorn, scheduler task) can share the same in-memory or file DB.
        options.setdefault("connect_args", {"check_same_thread": False})
        engine = create_async_engine(url, **options)
        event.listen(engine.sync_engine, "connect", _apply_sqlite_pragmas)
        return engine

    options.setdefault("pool_pre_ping", True)
    options.update(_pool_kwargs_from_env())
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
