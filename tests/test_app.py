"""Application bootstrap tests (no network access)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.main import _validate_token, build_application


def _settings(token: str) -> Settings:
    return Settings(
        bot_token=token,
        database_url="sqlite://",
        gpa_calculator_url="https://example.com",
        admin_ids=frozenset({1}),
        timezone="Asia/Tehran",
        log_level="INFO",
        log_dir=Path("."),
    )


def test_token_validation_rejects_missing_token():
    with pytest.raises(SystemExit) as missing:
        _validate_token(_settings(""))
    assert "BOT_TOKEN" in str(missing.value)


def test_token_validation_rejects_placeholder():
    with pytest.raises(SystemExit) as placeholder:
        _validate_token(_settings("000000000-REPLACE-WITH-REAL-TOKEN"))
    assert "BOT_TOKEN" in str(placeholder.value)


def test_token_validation_accepts_a_real_looking_token():
    _validate_token(_settings("123456:TEST-TOKEN"))  # must not raise


def test_build_application_registers_handlers(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings("123456:TEST-TOKEN"))
    application = build_application()

    # group -1 (middleware), group 0 (features), group 1 (fallback)
    assert set(application.handlers.keys()) >= {-1, 0, 1}
    assert len(application.handlers[0]) > 0
    assert len(application.handlers[1]) == 1  # the text fallback stays last

    # every feature conversation must really be registered
    registered = {
        handler.name for handler in application.handlers[0] if getattr(handler, "name", None)
    }
    assert registered >= {
        "schedule_conversation",
        "course_conversation",
        "grades_conversation",
        "profile_conversation",
        "reminder_conversation",
        "notes_conversation",
        "links_conversation",
        "announcements_conversation",
        "calendar_conversation",
    }
