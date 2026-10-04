""">👤 پروفایل handler tests."""

from __future__ import annotations

from app.bot.handlers.profile import (
    on_field_chosen,
    on_value_received,
    show_profile,
)
from app.bot.keyboards.main_menu import PROFILE
from app.bot.middlewares import capture_user
from app.bot.states.profile_states import ProfileState
from app.database.database import get_session
from app.database.repositories import UserRepository
from tests.helpers import FakeContext, make_callback_update, make_text_update


async def _register(db, user_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=user_id), context)
    return context


async def test_profile_shows_empty_fields(db):
    context = await _register(db, 2001)
    state = await show_profile(make_text_update(PROFILE, user_id=2001), context)

    assert state == ProfileState.CHOOSING_FIELD
    text = context.sent_texts[-1]
    assert "پروفایل دانشجویی" in text
    assert "—" in text  # empty values are visible as a dash
    assert context.last_markup is not None  # edit buttons offered


async def test_full_edit_flow_saves_the_value(db):
    context = await _register(db, 2002)
    await show_profile(make_text_update(PROFILE, user_id=2002), context)

    state = await on_field_chosen(
        make_callback_update("profile:field:student_number"), context
    )
    assert state == ProfileState.ENTERING_VALUE
    assert "شماره دانشجویی" in context.sent_texts[-1]

    state = await on_value_received(make_text_update("402123456", user_id=2002), context)
    assert state == ProfileState.CHOOSING_FIELD
    assert "با موفقیت ذخیره شد" in context.sent_texts[-2]

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(2002)
    assert user.student_number == "402123456"


async def test_invalid_value_shows_a_hint_and_keeps_the_state(db):
    context = await _register(db, 2003)
    await show_profile(make_text_update(PROFILE, user_id=2003), context)
    await on_field_chosen(make_callback_update("profile:field:student_number"), context)

    state = await on_value_received(make_text_update("سه", user_id=2003), context)

    assert state == ProfileState.ENTERING_VALUE
    assert "عدد" in context.sent_texts[-1]

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(2003)
    assert user.student_number is None


async def test_persian_digits_are_accepted(db):
    context = await _register(db, 2004)
    await show_profile(make_text_update(PROFILE, user_id=2004), context)
    await on_field_chosen(make_callback_update("profile:field:student_number"), context)
    state = await on_value_received(make_text_update("۴۰۲۱۲۳۴۵۶", user_id=2004), context)

    assert state == ProfileState.CHOOSING_FIELD
    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(2004)
    assert user.student_number == "402123456"


async def test_cancel_returns_to_the_menu(db):
    context = await _register(db, 2005)
    await show_profile(make_text_update(PROFILE, user_id=2005), context)
    await on_field_chosen(make_callback_update("profile:field:university"), context)

    state = await on_value_received(make_text_update("❌ لغو", user_id=2005), context)

    assert state == ProfileState.CHOOSING_FIELD
    assert "پروفایل دانشجویی" in context.sent_texts[-1]
    assert "profile_field" not in context.user_data
