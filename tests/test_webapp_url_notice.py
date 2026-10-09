"""WEBAPP_URL rotation: users get a fresh menu with the new Mini App link.

Quick tunnels change their address on every restart; ``web_app`` buttons
embed the URL at send time and never ping the bot, so without this push
users keep tapping a dead link.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.keyboards.main_menu import MINI_APP
from app.config import reset_settings_cache
from app.database.database import get_session
from app.database.repositories import UserRepository
from app.scheduler import run_webapp_url_notice


def _application() -> SimpleNamespace:
    return SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))


async def _user(telegram_id: int) -> int:
    async with get_session() as session:
        user, _ = await UserRepository(session).get_or_create_from_telegram(
            telegram_id=telegram_id,
            username=f"u{telegram_id}",
            first_name="Student",
            last_name=None,
        )
        return user.id


@pytest.fixture
def restore_webapp_url(monkeypatch):
    yield
    monkeypatch.setenv("WEBAPP_URL", "")
    reset_settings_cache()


async def test_url_change_notifies_every_user_exactly_once(
    db, monkeypatch, tmp_path, restore_webapp_url
):
    monkeypatch.setenv("WEBAPP_URL", "https://new-url.trycloudflare.com")
    reset_settings_cache()
    marker = tmp_path / "webapp_url"
    await _user(8801)
    await _user(8802)
    application = _application()

    assert await run_webapp_url_notice(application, marker=marker) is True

    assert application.bot.send_message.await_count == 2
    kwargs = application.bot.send_message.await_args.kwargs
    assert kwargs["reply_markup"].keyboard[0][0].text == MINI_APP
    assert (
        kwargs["reply_markup"].keyboard[0][0].web_app.url
        == "https://new-url.trycloudflare.com"
    )
    assert marker.read_text(encoding="utf-8") == "https://new-url.trycloudflare.com"

    # same address again: nothing is pushed
    assert await run_webapp_url_notice(application, marker=marker) is False
    assert application.bot.send_message.await_count == 2


async def test_one_blocked_chat_does_not_stop_the_notice(
    db, monkeypatch, tmp_path, restore_webapp_url
):
    monkeypatch.setenv("WEBAPP_URL", "https://new-url.trycloudflare.com")
    reset_settings_cache()
    await _user(8803)
    await _user(8804)
    application = _application()
    application.bot.send_message.side_effect = [RuntimeError("blocked"), None]

    assert await run_webapp_url_notice(
        application, marker=tmp_path / "webapp_url"
    ) is True
    assert application.bot.send_message.await_count == 2


async def test_no_notice_without_a_webapp_url(db, tmp_path, restore_webapp_url):
    # conftest clears WEBAPP_URL for tests
    application = _application()

    assert await run_webapp_url_notice(application, marker=tmp_path / "u") is False
    application.bot.send_message.assert_not_awaited()
    assert not (tmp_path / "u").exists()
