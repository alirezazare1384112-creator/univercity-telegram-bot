"""🛠 پنل ادمین tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

from telegram.ext import ConversationHandler

from app.bot.handlers import admin as admin_module
from app.bot.handlers.admin import (
    BROADCAST_PROMPT,
    PANEL_TITLE,
    cmd_admin,
    on_broadcast_start,
    on_broadcast_text,
    on_stats,
    on_sync,
    on_users,
)
from app.bot.middlewares import capture_user
from app.bot.states.admin_states import AdminState
from app.database.database import get_session
from app.database.repositories import AdminRepository
from tests.helpers import FakeContext, make_callback_update, make_text_update

ADMIN_ID = 777777777
OTHER_ID = 888888888
STRANGER_ID = 999999999


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    context.bot.send_message.reset_mock()
    return context


async def _make_admin(telegram_id: int) -> None:
    async with get_session() as session:
        await AdminRepository(session).upsert(
            telegram_id=telegram_id, username="boss", first_name="Boss"
        )


async def test_non_admin_is_ignored(db):
    context = await _register(STRANGER_ID)

    state = await cmd_admin(make_text_update("/admin", user_id=STRANGER_ID), context)

    assert state is None
    assert context.sent_messages == []


async def test_admin_opens_the_panel(db):
    await _make_admin(ADMIN_ID)
    context = await _register(ADMIN_ID)

    state = await cmd_admin(make_text_update("/admin", user_id=ADMIN_ID), context)

    assert state == AdminState.MENU
    assert PANEL_TITLE in context.sent_texts[-1]
    texts = [
        button.text
        for row in context.last_markup.inline_keyboard
        for button in row
    ]
    for label in (
        admin_module.STATS,
        admin_module.USERS,
        admin_module.BROADCAST,
        admin_module.SYNC,
        admin_module.CLOSE,
    ):
        assert label in texts


async def test_stats_show_registered_counts(db):
    await _make_admin(ADMIN_ID)
    context = await _register(ADMIN_ID)

    state = await on_stats(make_callback_update("adm:stats", user_id=ADMIN_ID), context)

    assert state == AdminState.MENU
    text = context.sent_texts[-1]
    assert "کاربران: 1 (فعال: 1)" in text
    assert "ادمین" in text
    assert "اطلاعیه" in text


async def test_users_list_shows_everyone(db):
    await _make_admin(ADMIN_ID)
    context = await _register(ADMIN_ID)
    await _register(OTHER_ID)

    state = await on_users(make_callback_update("adm:users", user_id=ADMIN_ID), context)

    assert state == AdminState.MENU
    text = context.sent_texts[-1]
    assert "کل: 2" in text
    assert f"tg: {OTHER_ID}" in text


async def test_broadcast_reaches_every_active_user(db):
    await _make_admin(ADMIN_ID)
    context = await _register(ADMIN_ID)
    await _register(OTHER_ID)

    state = await on_broadcast_start(
        make_callback_update("adm:broadcast", user_id=ADMIN_ID), context
    )
    assert state == AdminState.WAITING
    assert BROADCAST_PROMPT in context.sent_texts[-1]

    state = await on_broadcast_text(
        make_text_update("پیام آزمایشی", user_id=ADMIN_ID), context
    )

    assert state == AdminState.MENU
    delivered = {
        call.kwargs["chat_id"]
        for call in context.bot.send_message.call_args_list
        if call.kwargs.get("text") == "پیام آزمایشی"
    }
    assert delivered == {ADMIN_ID, OTHER_ID}
    assert "برای 2 کاربر" in context.sent_texts[-1]


async def test_sync_reports_the_imported_count(db, monkeypatch):
    await _make_admin(ADMIN_ID)
    context = await _register(ADMIN_ID)
    monkeypatch.setattr(admin_module, "sync_channels", AsyncMock(return_value=3))

    state = await on_sync(make_callback_update("adm:sync", user_id=ADMIN_ID), context)

    assert state == AdminState.MENU
    assert "3 اطلاعیه" in context.sent_texts[-1]


async def test_callback_from_a_stranger_is_rejected(db):
    context = await _register(STRANGER_ID)

    state = await on_stats(make_callback_update("adm:stats", user_id=STRANGER_ID), context)

    assert state == ConversationHandler.END
    assert not any(PANEL_TITLE in text for text in context.sent_texts)
