"""📆 تقویم tests: jalali date wizard, done toggle, CRUD and scope."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jdatetime

from app.bot.handlers.calendar_events import (
    build_conversation,
    calendar_menu,
    on_add_clicked,
    on_back,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_done_clicked,
    on_edit_clicked,
    on_open,
    on_open_done,
    on_skip_clicked,
    on_toggle_clicked,
    on_wizard_text,
)
from app.bot.keyboards.main_menu import CALENDAR
from app.bot.middlewares import capture_user
from app.bot.states.calendar_states import CalendarState
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import CalendarEventRepository, UserRepository
from app.utils.datetime_utils import (
    format_jalali_date,
    get_tz,
    parse_user_date,
    relative_date_label,
)
from tests.helpers import FakeContext, make_callback_update, make_text_update

TZ = "Asia/Tehran"


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _create_event(
    context: FakeContext,
    telegram_id: int,
    *,
    title: str = "امتحان پایگاه داده",
    raw_date: str = "1404/07/12",
    event_time: str | None = "18:30",
    description: str | None = "سالن ۳",
) -> int:
    """Drive the whole creation wizard and return the new event id."""
    user_id = context.user_data.get("user_id")
    async with get_session() as session:
        known_ids = {e.id for e in await CalendarEventRepository(session).list_by_user(user_id)}

    await calendar_menu(make_text_update(CALENDAR, user_id=telegram_id), context)
    await on_add_clicked(make_callback_update("cal:add", user_id=telegram_id), context)
    await on_wizard_text(make_text_update(title, user_id=telegram_id), context)
    await on_wizard_text(make_text_update(raw_date, user_id=telegram_id), context)
    if event_time is None:
        await on_skip_clicked(make_callback_update("cal:skip", user_id=telegram_id), context)
    else:
        await on_wizard_text(make_text_update(event_time, user_id=telegram_id), context)
    if description is None:
        await on_skip_clicked(make_callback_update("cal:skip", user_id=telegram_id), context)
    else:
        await on_wizard_text(make_text_update(description, user_id=telegram_id), context)

    async with get_session() as session:
        events = await CalendarEventRepository(session).list_by_user(user_id)
    created = [event for event in events if event.id not in known_ids]
    assert len(created) == 1
    return created[0].id


# --- menu ---------------------------------------------------------------
async def test_empty_menu_invites_the_student(db):
    context = await _register(8801)

    state = await calendar_menu(make_text_update(CALENDAR, user_id=8801), context)

    assert state == CalendarState.MENU
    assert "هنوز رویدادی ثبت نکرده‌ای" in context.sent_texts[-1]
    assert "➕ رویداد جدید" in str(context.last_markup)
    done_buttons = [
        button
        for row in context.last_markup.inline_keyboard
        for button in row
        if button.callback_data == "cal:done"
    ]
    assert done_buttons and done_buttons[0].text.endswith("(0)")


# --- creation -----------------------------------------------------------
async def test_full_wizard_saves_date_time_and_description(db):
    context = await _register(8802)
    event_id = await _create_event(context, 8802)

    assert any("✅ رویداد ذخیره شد" in text for text in context.sent_texts)
    detail = context.sent_texts[-1]
    # 1404/07/12 is a Saturday
    assert "🗓 تاریخ: 1404/07/12 (شنبه)" in detail
    assert "ساعت 18:30" in detail
    assert "سالن ۳" in detail
    assert "⏳ در انتظار" in detail

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        event = await CalendarEventRepository(session).get(event_id, user_id)
    assert event.title == "امتحان پایگاه داده"
    assert jdatetime.date.fromgregorian(date=event.event_date) == jdatetime.date(1404, 7, 12)
    assert event.event_time is not None
    assert event.event_time.hour == 18 and event.event_time.minute == 30
    assert event.is_done is False


async def test_relative_date_is_stored_as_a_real_day(db):
    context = await _register(8803)
    event_id = await _create_event(context, 8803, raw_date="فردا", description=None)

    tz = get_settings().timezone
    _, expected, _ = parse_user_date("فردا", tz)
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        event = await CalendarEventRepository(session).get(event_id, user_id)
    assert event.event_date == expected
    assert "— فردا" in context.sent_texts[-1]


async def test_persian_digits_date_is_accepted(db):
    context = await _register(8804)
    event_id = await _create_event(
        context, 8804, title="جلسه مشاوره", raw_date="۱۴۰۴/۰۷/۱۲"
    )

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        event = await CalendarEventRepository(session).get(event_id, user_id)
    assert jdatetime.date.fromgregorian(date=event.event_date) == jdatetime.date(1404, 7, 12)


async def test_skipped_time_makes_an_all_day_event(db):
    context = await _register(8805)
    event_id = await _create_event(context, 8805, event_time=None, description=None)

    assert "تمام روز" in context.sent_texts[-1]
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        event = await CalendarEventRepository(session).get(event_id, user_id)
    assert event.event_time is None
    assert event.description is None


async def test_invalid_date_is_rejected(db):
    context = await _register(8806)
    await calendar_menu(make_text_update(CALENDAR, user_id=8806), context)
    await on_add_clicked(make_callback_update("cal:add", user_id=8806), context)
    await on_wizard_text(make_text_update("عنوان آزمایشی", user_id=8806), context)

    state = await on_wizard_text(make_text_update("1404/13/1", user_id=8806), context)

    assert state == CalendarState.WIZARD
    assert "⚠️" in context.sent_texts[-1]
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await CalendarEventRepository(session).count(user_id) == 0


async def test_invalid_time_is_rejected(db):
    context = await _register(8807)
    await calendar_menu(make_text_update(CALENDAR, user_id=8807), context)
    await on_add_clicked(make_callback_update("cal:add", user_id=8807), context)
    await on_wizard_text(make_text_update("عنوان", user_id=8807), context)
    await on_wizard_text(make_text_update("فردا", user_id=8807), context)

    state = await on_wizard_text(make_text_update("25:99", user_id=8807), context)

    assert state == CalendarState.WIZARD
    assert "⚠️" in context.sent_texts[-1]


# --- lists --------------------------------------------------------------
async def test_menu_lists_upcoming_events_with_jalali_date(db):
    context = await _register(8808)
    await _create_event(context, 8808, title="تحویل پروژه")

    context.bot.send_message.reset_mock()
    state = await calendar_menu(make_text_update(CALENDAR, user_id=8808), context)

    assert state == CalendarState.MENU
    assert "📌 تحویل پروژه" in context.sent_texts[-1]
    assert "1404/07/12 (شنبه)" in context.sent_texts[-1]


# --- done toggle --------------------------------------------------------
async def test_done_toggle_moves_the_event_between_lists(db):
    context = await _register(8809)
    event_id = await _create_event(context, 8809, title="کار تمام‌شده")

    state = await on_toggle_clicked(
        make_callback_update(f"cal:toggle:{event_id}", user_id=8809), context
    )
    assert state == CalendarState.DETAIL
    assert any("✅ انجام شد" in text for text in context.sent_texts)
    assert "وضعیت: ✅ انجام شده" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        repo = CalendarEventRepository(session)
        assert await repo.count(user_id) == 0
        assert await repo.count(user_id, done=True) == 1

    # gone from the upcoming menu, visible on the done screen
    context.bot.send_message.reset_mock()
    await calendar_menu(make_text_update(CALENDAR, user_id=8809), context)
    assert "کار تمام‌شده" not in context.sent_texts[-1]

    context.bot.send_message.reset_mock()
    state = await on_done_clicked(
        make_callback_update("cal:done", user_id=8809), context
    )
    assert state == CalendarState.DONE
    assert "✅ کار تمام‌شده" in context.sent_texts[-1]

    # back from the done list returns to the done list
    state = await on_open_done(
        make_callback_update(f"cal:open_done:{event_id}", user_id=8809), context
    )
    assert state == CalendarState.DETAIL
    state = await on_back(make_callback_update("cal:back", user_id=8809), context)
    assert state == CalendarState.DONE


async def test_undo_puts_the_event_back(db):
    context = await _register(8810)
    event_id = await _create_event(context, 8810, title="قابل برگشت")

    await on_toggle_clicked(
        make_callback_update(f"cal:toggle:{event_id}", user_id=8810), context
    )
    state = await on_toggle_clicked(
        make_callback_update(f"cal:toggle:{event_id}", user_id=8810), context
    )

    assert state == CalendarState.DETAIL
    assert any("برگشت" in text for text in context.sent_texts)
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await CalendarEventRepository(session).count(user_id) == 1
        assert await CalendarEventRepository(session).count(user_id, done=True) == 0


# --- edit / delete / scope ---------------------------------------------
async def test_edit_title(db):
    context = await _register(8811)
    event_id = await _create_event(context, 8811)

    state = await on_edit_clicked(
        make_callback_update(f"cal:edit:{event_id}:title", user_id=8811), context
    )
    assert state == CalendarState.WIZARD
    assert "عنوان رویداد" in context.sent_texts[-1]

    state = await on_wizard_text(make_text_update("عنوان تازه", user_id=8811), context)
    assert state == CalendarState.DETAIL
    assert any("✅ تغییرات ذخیره شد" in text for text in context.sent_texts)

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        event = await CalendarEventRepository(session).get(event_id, user_id)
    assert event.title == "عنوان تازه"
    assert jdatetime.date.fromgregorian(date=event.event_date) == jdatetime.date(1404, 7, 12)


async def test_delete_requires_confirmation(db):
    context = await _register(8812)
    event_id = await _create_event(context, 8812)

    state = await on_delete_clicked(
        make_callback_update(f"cal:delete:{event_id}", user_id=8812), context
    )
    assert state == CalendarState.DETAIL
    assert "حذف شود" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    await on_delete_cancelled(
        make_callback_update("cal:delete:no", user_id=8812), context
    )
    async with get_session() as session:
        assert await CalendarEventRepository(session).get(event_id, user_id) is not None

    await on_delete_clicked(
        make_callback_update(f"cal:delete:{event_id}", user_id=8812), context
    )
    state = await on_delete_confirmed(
        make_callback_update(f"cal:delete:{event_id}:yes", user_id=8812), context
    )
    assert state == CalendarState.MENU
    async with get_session() as session:
        assert await CalendarEventRepository(session).get(event_id, user_id) is None


async def test_one_student_cannot_open_another_students_event(db):
    context_a = await _register(8813)
    event_id = await _create_event(context_a, 8813, title="خصوصی")

    context_b = await _register(8814)
    state = await on_open(
        make_callback_update(f"cal:open:{event_id}", user_id=8814), context_b
    )

    assert state == CalendarState.MENU
    assert any("پیدا نشد" in text for text in context_b.sent_texts)
    assert "خصوصی" not in "\n".join(context_b.sent_texts)


async def test_deleting_a_user_removes_his_events(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=8815, username="u", first_name="U", last_name=None
    )
    await session.flush()
    await CalendarEventRepository(session).create(
        user_id=user.id, title="I", event_date=datetime.now(UTC).date()
    )
    await session.commit()

    await session.delete(user)
    await session.commit()

    assert await CalendarEventRepository(session).count(user.id) == 0


# --- helpers ------------------------------------------------------------
def test_parse_user_date_accepts_jalali_and_relative():
    ok, parsed, _ = parse_user_date("1404/07/12", TZ)
    assert ok and parsed.year == 2025 and parsed.month == 10 and parsed.day == 4

    ok, parsed, _ = parse_user_date("۱۴۰۴/۰۷/۱۲", TZ)
    assert ok and parsed is not None

    ok, parsed, _ = parse_user_date("فردا", TZ)
    assert ok and parsed == datetime.now(UTC).astimezone(get_tz(TZ)).date() + timedelta(days=1)


def test_parse_user_date_rejects_bad_input():
    for bad in ("", "فردا بعد از ظهر", "1404/13/1", "تاریخ"):
        ok, parsed, error = parse_user_date(bad, TZ)
        assert not ok, bad
        assert parsed is None
        assert error


def test_format_jalali_date_includes_the_weekday():
    assert format_jalali_date(datetime(2025, 10, 4).date()) == "1404/07/12 (شنبه)"
    assert format_jalali_date(datetime(2025, 10, 10).date()).endswith("(جمعه)")


def test_relative_date_label():
    today = datetime.now(UTC).astimezone(get_tz(TZ)).date()
    assert relative_date_label(today, TZ) == "امروز"
    assert relative_date_label(today + timedelta(days=1), TZ) == "فردا"
    assert relative_date_label(today + timedelta(days=2), TZ) == "پس‌فردا"
    assert relative_date_label(today - timedelta(days=1), TZ) == "دیروز"
    assert relative_date_label(today + timedelta(days=9), TZ) == ""


def test_conversation_covers_the_four_states():
    handler = build_conversation()
    assert set(handler.states) == {
        CalendarState.MENU,
        CalendarState.DONE,
        CalendarState.DETAIL,
        CalendarState.WIZARD,
    }
