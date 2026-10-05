"""برنامه هفتگی tests."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from telegram.ext import MessageHandler

from app.bot.handlers.schedule import (
    build_conversation,
    on_add_clicked,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_photo_received,
    on_text_while_waiting,
    schedule_menu,
)
from app.bot.keyboards.main_menu import SCHEDULE
from app.bot.middlewares import capture_user
from app.bot.states.schedule_states import ScheduleState
from app.database.database import get_session
from app.database.models import WeeklySchedule
from app.database.repositories import UserRepository, WeeklyScheduleRepository
from tests.helpers import (
    FakeContext,
    make_callback_update,
    make_document_update,
    make_photo_update,
    make_text_update,
)


async def _register(user_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=user_id), context)
    return context


async def test_menu_without_schedule_asks_for_a_photo(db):
    context = await _register(3001)
    state = await schedule_menu(make_text_update(SCHEDULE, user_id=3001), context)

    assert state == ScheduleState.WAITING_PHOTO
    assert "هنوز برنامه" in context.sent_texts[-1]


async def test_sending_a_photo_stores_it(db):
    context = await _register(3002)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3002), context)
    await on_add_clicked(make_callback_update("schedule:add", user_id=3002), context)

    state = await on_photo_received(
        make_photo_update(file_id="FILE_A", caption="term 1404", user_id=3002), context
    )
    assert state == ScheduleState.MENU
    assert any("با موفقیت ذخیره شد" in text for text in context.sent_texts)

    async with get_session() as session:
        repo = WeeklyScheduleRepository(session)
        user = await UserRepository(session).get_by_telegram_id(3002)
        schedule = await repo.get_active(user.id)
    assert schedule is not None
    assert schedule.telegram_file_id == "FILE_A"
    assert schedule.file_type == "photo"
    assert schedule.caption == "term 1404"
    assert schedule.is_active is True


async def test_schedule_is_resent_from_the_stored_file_id(db):
    context = await _register(3003)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3003), context)
    await on_photo_received(make_photo_update(file_id="FILE_B", user_id=3003), context)

    context.bot.send_photo.reset_mock()
    state = await schedule_menu(make_text_update(SCHEDULE, user_id=3003), context)

    assert state == ScheduleState.MENU
    assert context.bot.send_photo.await_count == 1
    assert context.bot.send_photo.call_args.kwargs["photo"] == "FILE_B"


async def test_replacing_the_schedule_keeps_a_single_row(db):
    context = await _register(3004)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3004), context)
    await on_photo_received(make_photo_update(file_id="OLD", user_id=3004), context)
    await on_photo_received(make_photo_update(file_id="NEW", user_id=3004), context)

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(3004)
        assert await WeeklyScheduleRepository(session).count(user.id) == 1
        schedule = await WeeklyScheduleRepository(session).get_active(user.id)
    assert schedule.telegram_file_id == "NEW"


async def test_image_document_is_accepted(db):
    context = await _register(3005)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3005), context)
    state = await on_photo_received(
        make_document_update(file_id="DOC_1", user_id=3005), context
    )
    assert state == ScheduleState.MENU

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(3005)
        schedule = await WeeklyScheduleRepository(session).get_active(user.id)
    assert schedule.file_type == "document"
    assert schedule.telegram_file_id == "DOC_1"


async def test_plain_text_while_waiting_shows_a_hint(db):
    context = await _register(3006)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3006), context)
    state = await on_text_while_waiting(make_text_update("salam", user_id=3006), context)

    assert state == ScheduleState.WAITING_PHOTO
    assert "عکس" in context.sent_texts[-1]


async def test_add_button_while_awaiting_reprompts(db):
    """The empty-state button must never be a dead end."""
    context = await _register(3010)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3010), context)

    state = await on_add_clicked(
        make_callback_update("schedule:add", user_id=3010), context
    )

    assert state == ScheduleState.WAITING_PHOTO
    assert "عکس برنامه" in context.sent_texts[-1]


async def test_photo_sent_from_the_menu_replaces_the_schedule(db):
    context = await _register(3011)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3011), context)
    await on_photo_received(make_photo_update(file_id="OLD", user_id=3011), context)

    state = await on_photo_received(
        make_photo_update(file_id="NEW", user_id=3011), context
    )
    assert state == ScheduleState.MENU

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(3011)
        schedule = await WeeklyScheduleRepository(session).get_active(user.id)
    assert schedule.telegram_file_id == "NEW"


def test_wiring_keeps_every_schedule_button_alive():
    """The empty-state button and stray files must never go unanswered."""
    handler = build_conversation()

    def patterns(state):
        return [
            item.pattern.pattern
            for item in handler.states[state]
            if getattr(item, "pattern", None) is not None
        ]

    assert r"^schedule:add$" in patterns(ScheduleState.WAITING_PHOTO)

    photo = make_photo_update(user_id=1)
    pdf = make_document_update(user_id=1, mime_type="application/pdf")
    for state in (ScheduleState.MENU, ScheduleState.WAITING_PHOTO):
        for update in (photo, pdf):
            assert any(
                isinstance(item, MessageHandler) and item.filters.check_update(update)
                for item in handler.states[state]
            ), f"{state} must accept files"


async def test_cancel_stops_the_upload(db):
    context = await _register(3007)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3007), context)
    state = await on_text_while_waiting(make_text_update("❌ لغو", user_id=3007), context)

    assert state == ScheduleState.WAITING_PHOTO  # nothing stored yet
    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(3007)
        assert await WeeklyScheduleRepository(session).get_active(user.id) is None


async def test_delete_flow_with_confirmation(db):
    context = await _register(3008)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3008), context)
    await on_photo_received(make_photo_update(file_id="FILE_C", user_id=3008), context)

    state = await on_delete_clicked(
        make_callback_update("schedule:delete", user_id=3008), context
    )
    assert state == ScheduleState.MENU
    assert "حذف شود" in context.sent_texts[-1]

    await on_delete_confirmed(
        make_callback_update("schedule:delete:yes", user_id=3008), context
    )
    assert "حذف شد" in context.sent_texts[-1]

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(3008)
        assert await WeeklyScheduleRepository(session).get_active(user.id) is None


async def test_delete_can_be_cancelled(db):
    context = await _register(3009)
    await schedule_menu(make_text_update(SCHEDULE, user_id=3009), context)
    await on_photo_received(make_photo_update(file_id="FILE_D", user_id=3009), context)
    await on_delete_clicked(make_callback_update("schedule:delete", user_id=3009), context)

    state = await on_delete_cancelled(
        make_callback_update("schedule:delete:no", user_id=3009), context
    )
    assert state == ScheduleState.MENU

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(3009)
        assert await WeeklyScheduleRepository(session).get_active(user.id) is not None


async def test_database_allows_only_one_active_schedule(session):
    """The partial unique index is enforced by the database itself."""
    repo_user = UserRepository(session)
    user = await repo_user.upsert_from_telegram(
        telegram_id=4444, username="u", first_name="U", last_name=None
    )
    await session.flush()

    schedule_repo = WeeklyScheduleRepository(session)
    await schedule_repo.save(
        user_id=user.id,
        telegram_file_id="F1",
        file_unique_id="U1",
        file_type="photo",
    )
    await session.commit()

    # a second *active* row for the same user must be rejected
    session.add(WeeklySchedule(user_id=user.id, telegram_file_id="F2", is_active=True))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_a_user_removes_his_schedule(session):
    repo_user = UserRepository(session)
    user = await repo_user.upsert_from_telegram(
        telegram_id=5555, username="u", first_name="U", last_name=None
    )
    await session.flush()
    await WeeklyScheduleRepository(session).save(
        user_id=user.id, telegram_file_id="F1", file_unique_id="U1"
    )
    await session.commit()

    await session.delete(user)
    await session.commit()

    remaining = await WeeklyScheduleRepository(session).count(user.id)
    assert remaining == 0
