"""/start WebApp button: shown only for a valid https WEBAPP_URL."""

from __future__ import annotations

import pytest
from telegram import KeyboardButton

from app.bot.keyboards.main_menu import (
    MENU_LABELS,
    MINI_APP,
    main_menu_keyboard,
    mini_app_inline_keyboard,
)
from app.config import reset_settings_cache


def _labels(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def _set_webapp_url(monkeypatch, url: str) -> None:
    monkeypatch.setenv("WEBAPP_URL", url)
    reset_settings_cache()


@pytest.fixture
def restore_settings(monkeypatch):
    yield
    monkeypatch.setenv("WEBAPP_URL", "")
    reset_settings_cache()


async def test_button_hidden_without_webapp_url(restore_settings):
    assert MINI_APP not in _labels(main_menu_keyboard())


async def test_button_shown_for_https_url(monkeypatch, restore_settings):
    _set_webapp_url(monkeypatch, "https://bot.example.com/app")

    markup = main_menu_keyboard()
    labels = _labels(markup)
    assert labels[0] == MINI_APP
    assert MINI_APP not in MENU_LABELS  # the text filter must not catch it

    button = markup.keyboard[0][0]
    assert isinstance(button, KeyboardButton)
    assert button.web_app is not None
    assert button.web_app.url == "https://bot.example.com/app"


async def test_http_url_is_ignored(monkeypatch, restore_settings):
    _set_webapp_url(monkeypatch, "http://127.0.0.1:8000")

    labels = _labels(main_menu_keyboard())
    assert MINI_APP not in labels
    assert labels[0] == "📅 برنامه هفتگی"


async def test_trailing_slash_is_normalized(monkeypatch, restore_settings):
    _set_webapp_url(monkeypatch, "https://bot.example.com/app/")

    button = main_menu_keyboard().keyboard[0][0]
    assert button.web_app.url == "https://bot.example.com/app"


async def test_inline_button_hidden_without_webapp_url(restore_settings):
    assert mini_app_inline_keyboard() is None


async def test_inline_button_hidden_for_http_url(monkeypatch, restore_settings):
    _set_webapp_url(monkeypatch, "http://127.0.0.1:8000")
    assert mini_app_inline_keyboard() is None


async def test_inline_button_carries_the_web_app_url(monkeypatch, restore_settings):
    _set_webapp_url(monkeypatch, "https://bot.example.com/app")

    markup = mini_app_inline_keyboard()
    assert markup is not None
    button = markup.inline_keyboard[0][0]
    assert button.text == MINI_APP
    assert button.web_app is not None
    assert button.web_app.url == "https://bot.example.com/app"
