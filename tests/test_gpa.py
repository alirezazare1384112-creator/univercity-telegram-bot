"""🧮 محاسبه معدل handler tests."""

from __future__ import annotations

from pathlib import Path

from app.bot.handlers.gpa import _valid_url, gpa_back, gpa_handler
from app.bot.keyboards.main_menu import GPA
from tests.helpers import FakeContext, make_callback_update, make_text_update


def test_url_validation():
    assert _valid_url("https://example.com/gpa") is True
    assert _valid_url("http://localhost:8000") is True
    assert _valid_url("") is False
    assert _valid_url("not-a-url") is False
    assert _valid_url("ftp://example.com") is False


async def test_gpa_button_sends_the_url_from_settings(db, monkeypatch):
    import app.bot.handlers.gpa as module
    from app.config import Settings

    fake = Settings(
        bot_token="123456:TEST-TOKEN",
        database_url="sqlite://",
        gpa_calculator_url="https://gpa.example.ir/calc",
        admin_ids=frozenset(),
        timezone="Asia/Tehran",
        log_level="INFO",
        log_dir=Path("."),
    )
    monkeypatch.setattr(module, "get_settings", lambda: fake)

    context = FakeContext()
    await gpa_handler(make_text_update(GPA, user_id=6001), context)

    text = context.sent_texts[-1]
    markup = context.last_markup
    assert "https://gpa.example.ir/calc" in text
    url_buttons = [b for row in markup.inline_keyboard for b in row if b.url]
    assert url_buttons and url_buttons[0].url == "https://gpa.example.ir/calc"
    # the URL must come from settings, never be hard-coded in the text module
    assert "example.com" not in text


async def test_gpa_prefers_the_mini_app_page_when_webapp_is_configured(db, monkeypatch):
    import app.bot.handlers.gpa as module
    from app.config import Settings

    fake = Settings(
        bot_token="123456:TEST-TOKEN",
        database_url="sqlite://",
        gpa_calculator_url="https://gpa.example.ir/calc",
        webapp_url="https://bot.example.com/app",
        admin_ids=frozenset(),
        timezone="Asia/Tehran",
        log_level="INFO",
        log_dir=Path("."),
    )
    monkeypatch.setattr(module, "get_settings", lambda: fake)

    context = FakeContext()
    await gpa_handler(make_text_update(GPA, user_id=6004), context)

    markup = context.last_markup
    button = markup.inline_keyboard[0][0]
    assert button.web_app is not None
    assert button.web_app.url == "https://bot.example.com/app/?page=gpa"
    back = markup.inline_keyboard[1][0]
    assert back.callback_data == "gpa:back"
    # the built-in page wins over the external calculator
    assert all(b.web_app is None for row in markup.inline_keyboard for b in row[1:])


async def test_http_webapp_url_falls_back_to_the_external_site(db, monkeypatch):
    import app.bot.handlers.gpa as module
    from app.config import Settings

    fake = Settings(
        bot_token="123456:TEST-TOKEN",
        database_url="sqlite://",
        gpa_calculator_url="https://gpa.example.ir/calc",
        webapp_url="http://127.0.0.1:8000",
        admin_ids=frozenset(),
        timezone="Asia/Tehran",
        log_level="INFO",
        log_dir=Path("."),
    )
    monkeypatch.setattr(module, "get_settings", lambda: fake)

    context = FakeContext()
    await gpa_handler(make_text_update(GPA, user_id=6005), context)

    markup = context.last_markup
    button = markup.inline_keyboard[0][0]
    assert button.web_app is None
    assert button.url == "https://gpa.example.ir/calc"


async def test_gpa_without_url_shows_a_clear_message(db, monkeypatch):
    import app.bot.handlers.gpa as module
    from app.config import Settings

    fake = Settings(
        bot_token="123456:TEST-TOKEN",
        database_url="sqlite://",
        gpa_calculator_url="",
        admin_ids=frozenset(),
        timezone="Asia/Tehran",
        log_level="INFO",
        log_dir=Path("."),
    )
    monkeypatch.setattr(module, "get_settings", lambda: fake)

    context = FakeContext()
    await gpa_handler(make_text_update(GPA, user_id=6002), context)
    assert "تنظیم نشده" in context.sent_texts[-1]


async def test_gpa_back_returns_to_the_main_menu(db):
    from app.bot.keyboards.main_menu import MENU_LABELS

    context = FakeContext()
    await gpa_back(make_callback_update("gpa:back", user_id=6003), context)

    assert context.last_markup is not None
    labels = [[button.text for button in row] for row in context.last_markup.keyboard]
    assert [label for row in labels for label in row] == list(MENU_LABELS)
