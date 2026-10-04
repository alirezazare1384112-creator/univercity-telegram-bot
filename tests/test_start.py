"""/start, /help and main menu tests."""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup

from app.bot.handlers.start import cmd_help, cmd_start, fallback_text
from app.bot.keyboards.main_menu import MAIN_MENU_TITLE, MENU_LABELS, main_menu_keyboard
from app.bot.middlewares import capture_user
from app.database.database import get_session
from app.database.repositories import UserRepository
from tests.helpers import FakeContext, make_text_update


def _keyboard_labels(markup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.keyboard]


async def test_main_menu_contains_every_documented_entry():
    labels = _keyboard_labels(main_menu_keyboard())
    flat = [label for row in labels for label in row]
    assert flat == list(MENU_LABELS)


async def test_middleware_registers_the_user(db):
    update = make_text_update("/start", user_id=1001)
    context = FakeContext()

    await capture_user(update, context)

    assert context.user_data["is_new_user"] is True
    assert context.user_data["user_id"] >= 1

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(1001)
    assert user is not None
    assert user.username == "tester"
    assert user.is_active is True


async def test_second_update_does_not_create_a_second_row(db):
    update = make_text_update("/start", user_id=1002)
    context = FakeContext()
    await capture_user(update, context)
    await capture_user(make_text_update("/help", user_id=1002), context)

    async with get_session() as session:
        assert await UserRepository(session).count() == 1
    assert context.user_data["is_new_user"] is False


async def test_start_shows_the_main_menu(db):
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=1003), context)
    await cmd_start(make_text_update("/start", user_id=1003), context)

    assert context.bot.send_message.await_count == 1
    assert "دستیار دانشجو" in context.sent_texts[0]
    assert isinstance(context.last_markup, ReplyKeyboardMarkup)
    assert "📅 برنامه هفتگی" in _keyboard_labels(context.last_markup)[0]


async def test_start_greets_returning_user(db):
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=1004), context)
    await cmd_start(make_text_update("/start", user_id=1004), context)  # new user
    await capture_user(make_text_update("/start", user_id=1004), context)
    await cmd_start(make_text_update("/start", user_id=1004), context)  # returning

    assert "خوش برگشتی" in context.sent_texts[-1]


async def test_help_is_sent(db):
    context = FakeContext()
    await cmd_help(make_text_update("/help", user_id=1005), context)
    assert "/start" in context.sent_texts[0]


async def test_unknown_text_falls_back_to_the_menu(db):
    context = FakeContext()
    await fallback_text(make_text_update("سلام", user_id=1006), context)
    assert MAIN_MENU_TITLE in context.sent_texts[0]
    assert isinstance(context.last_markup, ReplyKeyboardMarkup)
