"""Configuration layer tests."""

from __future__ import annotations

from app.config import (
    Settings,
    _split_admin_ids,
    get_settings,
    normalize_database_url,
    reset_settings_cache,
)


def test_settings_are_loaded():
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.database_url.startswith("sqlite+aiosqlite://")
    assert settings.timezone == "Asia/Tehran"


def test_sqlite_relative_path_is_absolute_and_async():
    url = normalize_database_url("sqlite:///./data/bot.db")
    assert url.startswith("sqlite+aiosqlite:///")
    assert "data/bot.db" in url.replace("\\", "/")
    # resolved against the project root, not the current working directory
    assert ":/" in url.replace("\\", "/")


def test_memory_database_kept_as_is():
    assert normalize_database_url("sqlite:///:memory:") == "sqlite+aiosqlite:///:memory:"


def test_postgresql_url_gets_async_driver():
    url = normalize_database_url("postgresql://user:pass@localhost:5432/students")
    assert url == "postgresql+asyncpg://user:pass@localhost:5432/students"


def test_legacy_postgres_scheme_is_supported():
    url = normalize_database_url("postgres://user:pass@db/students")
    assert url.startswith("postgresql+asyncpg://")


def test_admin_ids_parsing():
    assert _split_admin_ids("1, 2,3") == frozenset({1, 2, 3})
    assert _split_admin_ids("") == frozenset()
    assert _split_admin_ids("abc, 7") == frozenset({7})  # invalid entries ignored


def test_is_admin_uses_telegram_id_only():
    settings = Settings(
        bot_token="x",
        database_url="sqlite://",
        gpa_calculator_url="https://example.com",
        admin_ids=frozenset({42}),
        timezone="Asia/Tehran",
        log_level="INFO",
        log_dir=get_settings().log_dir,
    )
    assert settings.is_admin(42) is True
    assert settings.is_admin(43) is False


def test_reset_settings_cache_is_safe():
    reset_settings_cache()
    assert get_settings().timezone == "Asia/Tehran"
