"""Application bootstrap tests (no network access)."""

from __future__ import annotations

import asyncio
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


async def test_serve_starts_and_stops_the_scheduler(monkeypatch):
    """_serve() drives PTB manually, so it must call post_init itself.

    Regression: PTB only runs post_init inside run_polling(); without this
    wiring the reminder poller never started in production.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import uvicorn

    import app.api as api_module
    import app.main as main_module
    import app.scheduler as scheduler_module

    started = AsyncMock()
    stopped = AsyncMock()
    monkeypatch.setattr(scheduler_module, "start_scheduler", started)
    monkeypatch.setattr(scheduler_module, "stop_scheduler", stopped)
    monkeypatch.setattr(main_module, "dispose_engine", AsyncMock())

    fake_app = SimpleNamespace(
        initialize=AsyncMock(),
        start=AsyncMock(),
        stop=AsyncMock(),
        shutdown=AsyncMock(),
        updater=SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock()),
    )
    monkeypatch.setattr(main_module, "build_application", lambda: fake_app)
    monkeypatch.setattr(api_module, "create_api", lambda application: object())

    class FakeServer:
        def __init__(self, config) -> None:
            pass

        async def serve(self) -> None:
            return None

    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    await main_module._serve(_settings("123456:TEST-TOKEN"))

    fake_app.initialize.assert_awaited_once()
    started.assert_awaited_once_with(fake_app)
    stopped.assert_awaited_once_with(fake_app)
    fake_app.shutdown.assert_awaited_once()


async def test_boot_retries_until_it_works(monkeypatch):
    """A blocked network must not kill the process: boot retries forever."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import app.main as main_module

    initialize = AsyncMock(
        side_effect=[RuntimeError("net down"), RuntimeError("net down"), None]
    )
    application = SimpleNamespace(
        initialize=initialize,
        updater=SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock()),
        start=AsyncMock(),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(main_module, "_post_init", AsyncMock())
    monkeypatch.setattr(main_module.asyncio, "sleep", AsyncMock())

    state: dict[str, bool] = {}
    await main_module._boot_forever(application, state)

    assert initialize.await_count == 3
    assert application.updater.start_polling.await_count == 1
    assert application.start.await_count == 1
    assert state == {"polling_started": True, "app_started": True}


async def test_a_hung_boot_attempt_is_capped_and_retried(monkeypatch):
    """A blackholed network must not hang one boot attempt forever."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import app.main as main_module

    async def flaky_initialize() -> None:
        if initialize_mock.await_count == 1:
            await asyncio.Event().wait()  # first call never returns on its own

    initialize_mock = AsyncMock(side_effect=flaky_initialize)
    updater = SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock())
    application = SimpleNamespace(
        initialize=initialize_mock, updater=updater, start=AsyncMock(),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(main_module, "_BOOT_ATTEMPT_SECONDS", 0.05)
    monkeypatch.setattr(main_module, "_post_init", AsyncMock())
    monkeypatch.setattr(main_module.asyncio, "sleep", AsyncMock())

    state: dict[str, bool] = {}
    await main_module._boot_forever(application, state)

    assert initialize_mock.await_count == 2
    updater.stop.assert_awaited()


async def test_scheduler_failure_does_not_retry_the_boot(monkeypatch):
    """Post-init errors are logged; polling must stay up without retries."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import app.main as main_module

    application = SimpleNamespace(
        initialize=AsyncMock(return_value=None),
        updater=SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock()),
        start=AsyncMock(),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(
        main_module, "_post_init", AsyncMock(side_effect=RuntimeError("sched down"))
    )
    monkeypatch.setattr(main_module.asyncio, "sleep", AsyncMock())

    state: dict[str, bool] = {}
    await main_module._boot_forever(application, state)

    assert application.initialize.await_count == 1
    assert application.start.await_count == 1
    assert state == {"polling_started": True, "app_started": True}
