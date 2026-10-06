"""Application configuration.

All secrets and environment specific values come from the `.env` file.
Nothing in this project hard-codes tokens, URLs or database credentials.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Project root = parent of the `app` package.
BASE_DIR: Path = Path(__file__).resolve().parent.parent

# Load `.env` from the project root (only once, at import time).
load_dotenv(BASE_DIR / ".env")

_SQLITE_PREFIXES = ("sqlite+aiosqlite:///", "sqlite:///")
_POSTGRES_PREFIXES = ("postgresql+asyncpg://", "postgresql://", "postgres://")
_ASYNC_POSTGRES_PREFIX = "postgresql+asyncpg://"


def normalize_database_url(raw_url: str) -> str:
    """Turn the URL from `.env` into an async SQLAlchemy URL.

    - ``sqlite:///...``      -> ``sqlite+aiosqlite:///...``  (development)
    - ``postgresql://...``   -> ``postgresql+asyncpg://...`` (production)

    Relative SQLite paths are resolved against the project root so the bot
    behaves the same no matter which folder it is started from.
    """
    url = (raw_url or "").strip()

    # ---- PostgreSQL -------------------------------------------------
    for prefix in _POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return _ASYNC_POSTGRES_PREFIX + url[len(prefix):]

    # ---- SQLite -----------------------------------------------------
    for prefix in _SQLITE_PREFIXES:
        if url.startswith(prefix):
            path_part = url[len(prefix):]
            if path_part in (":memory:", "") or path_part.startswith("file:"):
                return "sqlite+aiosqlite:///" + path_part
            path = Path(path_part)
            if not path.is_absolute():
                path = (BASE_DIR / path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return "sqlite+aiosqlite:///" + path.as_posix()

    # Already an async URL or an unknown scheme: return as is.
    return url


def _split_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for chunk in (raw or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError:
            logger.warning("Ignoring invalid ADMIN_IDS entry: %r", chunk)
    return frozenset(ids)


def _split_urls(raw: str) -> tuple[str, ...]:
    """Comma separated http(s) URLs; trailing slashes are dropped."""
    urls: list[str] = []
    for chunk in (raw or "").replace(";", ",").split(","):
        url = chunk.strip().rstrip("/")
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            logger.warning("Ignoring invalid EITAA_SYNC_URLS entry: %r", chunk)
            continue
        urls.append(url)
    return tuple(urls)


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable application settings loaded from the environment."""

    bot_token: str
    database_url: str
    gpa_calculator_url: str
    admin_ids: frozenset[int]
    timezone: str
    log_level: str
    log_dir: Path
    base_dir: Path = field(default=BASE_DIR)
    eitaa_sync_urls: tuple[str, ...] = ()
    eitaa_sync_seconds: int = 300
    webapp_url: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    webapp_auth_max_age: int = 86400

    def is_admin(self, telegram_id: int) -> bool:
        """Access to the admin panel is granted by Telegram id only."""
        return telegram_id in self.admin_ids

    @property
    def has_admins(self) -> bool:
        return len(self.admin_ids) > 0


def _read_settings() -> Settings:
    import os

    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    if not log_dir.is_absolute():
        log_dir = (BASE_DIR / log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    raw_sync = os.getenv("EITAA_SYNC_SECONDS", "").strip()
    try:
        sync_seconds = int(raw_sync) if raw_sync else 300
    except ValueError:
        logger.warning("Ignoring invalid EITAA_SYNC_SECONDS: %r", raw_sync)
        sync_seconds = 300
    sync_seconds = max(60, sync_seconds)

    def _read_int(raw: str, default: int, *, minimum: int) -> int:
        try:
            value = int(raw) if raw.strip() else default
        except ValueError:
            logger.warning("Ignoring invalid integer setting: %r", raw)
            return default
        return max(minimum, value)

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        database_url=normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./data/bot.db")),
        gpa_calculator_url=os.getenv("GPA_CALCULATOR_URL", "").strip(),
        admin_ids=_split_admin_ids(os.getenv("ADMIN_IDS", "")),
        timezone=os.getenv("TIMEZONE", "Asia/Tehran").strip() or "Asia/Tehran",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        log_dir=log_dir,
        eitaa_sync_urls=_split_urls(os.getenv("EITAA_SYNC_URLS", "")),
        eitaa_sync_seconds=sync_seconds,
        webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
        api_host=os.getenv("API_HOST", "").strip() or "127.0.0.1",
        api_port=_read_int(os.getenv("API_PORT", ""), 8000, minimum=1),
        webapp_auth_max_age=_read_int(os.getenv("WEBAPP_AUTH_MAX_AGE", ""), 86400, minimum=60),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process wide settings object (cached)."""
    return _read_settings()


def reset_settings_cache() -> None:
    """Used by tests that change environment variables."""
    get_settings.cache_clear()
