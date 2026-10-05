"""Cross-user isolation (IDOR) tests.

Project rule: every query that returns student data is bounded by the
telegram user who sent the update. Student B must never read or write
student A's rows - neither through a normal flow nor through a forged /
forwarded inline button (``callback_data`` is fully client controlled).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from telegram.ext import CallbackQueryHandler, ConversationHandler

from app.bot.handlers import courses as courses_module
from app.bot.handlers import grades as grades_module
from app.bot.handlers.calendar_events import build_conversation as calendar_conv
from app.bot.handlers.calendar_events import on_open as event_open
from app.bot.handlers.grades import on_add_clicked as grade_add
from app.bot.handlers.grades import on_delete_confirmed as grade_delete_confirmed
from app.bot.handlers.grades import on_edit_clicked as grade_edit
from app.bot.handlers.links import on_open as link_open
from app.bot.handlers.notes import notes_menu, on_course_chosen, on_file_received
from app.bot.handlers.notes import on_add_clicked as note_add
from app.bot.handlers.notes import on_skip_clicked as note_skip
from app.bot.handlers.notes import on_wizard_text as note_text
from app.bot.handlers.reminders import on_open as reminder_open
from app.bot.keyboards.main_menu import NOTES
from app.bot.middlewares import capture_user
from app.bot.states.grade_states import GradeState
from app.database.database import get_session
from app.database.repositories import (
    CalendarEventRepository,
    CourseRepository,
    GradeItemRepository,
    LinkRepository,
    NoteRepository,
    ReminderRepository,
    UserRepository,
    WeeklyScheduleRepository,
)
from tests.helpers import (
    FakeContext,
    make_callback_update,
    make_photo_update,
    make_text_update,
)

USER_A = 9101
USER_B = 9102


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _course_for(context: FakeContext, name: str = "پایگاه داده") -> int:
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        course = await CourseRepository(session).create(
            user_id=user_id, name=name, units=3
        )
        return course.id


# --- forged callback data ------------------------------------------------
async def test_forged_grades_add_cannot_write_into_a_foreign_course(db):
    """``grades:add:<other course>`` must not attach a mark to A's course."""
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    foreign_course = await _course_for(ctx_a)

    state = await grade_add(
        make_callback_update(f"grades:add:{foreign_course}", user_id=USER_B), ctx_b
    )

    assert state == GradeState.PICK_COURSE
    assert any("پیدا نشد" in text for text in ctx_b.sent_texts)
    async with get_session() as session:
        assert await GradeItemRepository(session).count(foreign_course) == 0
    # B's wizard must not have been seeded with the foreign id either
    assert ctx_b.user_data.get("grade_course_id") is None


async def test_forged_grade_edit_callback_is_ignored(db):
    """A handler invoked with a foreign item id cannot edit that item."""
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    course_a = await _course_for(ctx_a)

    async with get_session() as session:
        item = await GradeItemRepository(session).create(
            course_id=course_a, title="میان‌ترم", score=6.0, max_score=8.0
        )
        item_id = item.id

    # B has no verified course selection of their own
    state = await grade_edit(
        make_callback_update(f"grades:edit:{item_id}:score", user_id=USER_B), ctx_b
    )

    assert state == GradeState.WIZARD
    async with get_session() as session:
        stored = await GradeItemRepository(session).get(item_id, course_a)
    assert stored is not None and stored.score == 6.0  # untouched


async def test_forged_grade_delete_is_refused_without_a_verified_course(db):
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    course_a = await _course_for(ctx_a)

    async with get_session() as session:
        item = await GradeItemRepository(session).create(
            course_id=course_a, title="تمرین", score=1.0, max_score=2.0
        )
        item_id = item.id

    state = await grade_delete_confirmed(
        make_callback_update(f"grades:delete:{item_id}:yes", user_id=USER_B), ctx_b
    )

    assert state == ConversationHandler.END
    async with get_session() as session:
        assert await GradeItemRepository(session).count(course_a) == 1  # still there


async def test_forged_note_course_cannot_link_to_a_foreign_course(db):
    """Choosing A's course id while adding a note must not link it."""
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    foreign_course = await _course_for(ctx_a)
    user_b = ctx_b.user_data["user_id"]

    await notes_menu(make_text_update(NOTES, user_id=USER_B), ctx_b)
    await note_add(make_callback_update("note:add", user_id=USER_B), ctx_b)
    await note_text(make_text_update("جزوه من", user_id=USER_B), ctx_b)
    await on_file_received(make_photo_update(user_id=USER_B), ctx_b)

    state = await on_course_chosen(
        make_callback_update(f"note:course:{foreign_course}", user_id=USER_B), ctx_b
    )

    assert state is not None  # stayed inside the wizard
    assert any("پیدا نشد" in text for text in ctx_b.sent_texts)

    # finish the wizard properly and check nothing leaked into A's course
    await on_course_chosen(
        make_callback_update("note:course:none", user_id=USER_B), ctx_b
    )
    await note_skip(make_callback_update("note:skip", user_id=USER_B), ctx_b)

    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user_b)
    assert len(notes) == 1
    assert notes[0].course_id is None


async def test_foreign_reminder_event_and_link_ids_are_not_readable(db):
    """Clicking another student's ids resolves to "not found", never data."""
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    user_a = ctx_a.user_data["user_id"]

    async with get_session() as session:
        reminder = await ReminderRepository(session).create(
            user_id=user_a,
            title="جلسه",
            reminder_datetime=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
            repeat_type="NONE",
        )
        event = await CalendarEventRepository(session).create(
            user_id=user_a, title="امتحان", event_date=datetime.now(UTC).date()
        )
        link = await LinkRepository(session).create(
            user_id=user_a, title="گلستان", url="https://golestan.uni.ir"
        )
        reminder_id, event_id, link_id = reminder.id, event.id, link.id

    await reminder_open(
        make_callback_update(f"rem:open:{reminder_id}", user_id=USER_B), ctx_b
    )
    assert any("پیدا نشد" in text for text in ctx_b.sent_texts)

    await event_open(
        make_callback_update(f"cal:open:{event_id}", user_id=USER_B), ctx_b
    )
    assert any("پیدا نشد" in text for text in ctx_b.sent_texts)

    await link_open(
        make_callback_update(f"link:open:{link_id}", user_id=USER_B), ctx_b
    )
    assert any("پیدا نشد" in text for text in ctx_b.sent_texts)


# --- repository level ----------------------------------------------------
async def test_repositories_are_scoped_by_user(db):
    """The scoped getters must return ``None`` for the other student."""
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    user_a = ctx_a.user_data["user_id"]
    user_b = ctx_b.user_data["user_id"]

    async with get_session() as session:
        course = await CourseRepository(session).create(
            user_id=user_a, name="DB", units=3
        )
        item = await GradeItemRepository(session).create(
            course_id=course.id, title="Mid", score=6.0, max_score=8.0
        )
        note = await NoteRepository(session).create(
            user_id=user_a,
            title="n",
            file_type="photo",
            file_id="f",
            course_id=course.id,
        )
        reminder = await ReminderRepository(session).create(
            user_id=user_a,
            title="r",
            reminder_datetime=datetime.now(UTC).replace(tzinfo=None),
            repeat_type="NONE",
        )
        event = await CalendarEventRepository(session).create(
            user_id=user_a, title="e", event_date=datetime.now(UTC).date()
        )
        link = await LinkRepository(session).create(
            user_id=user_a, title="l", url="https://uni.ir"
        )
        await WeeklyScheduleRepository(session).save(
            user_id=user_a, telegram_file_id="file", file_unique_id=None
        )
        ids = {
            "course": course.id,
            "item": item.id,
            "note": note.id,
            "reminder": reminder.id,
            "event": event.id,
            "link": link.id,
        }

    async with get_session() as session:
        assert await CourseRepository(session).get(ids["course"], user_b) is None
        assert await NoteRepository(session).get(ids["note"], user_b) is None
        assert await ReminderRepository(session).get(ids["reminder"], user_b) is None
        assert await CalendarEventRepository(session).get(ids["event"], user_b) is None
        assert await LinkRepository(session).get(ids["link"], user_b) is None
        assert await WeeklyScheduleRepository(session).get_active(user_b) is None
        # grade items are keyed by course; B can never reach A's course id
        assert await CourseRepository(session).get(ids["course"], user_b) is None
        assert await GradeItemRepository(session).get(ids["item"], ids["course"])

    # and every list is empty for the other student
    async with get_session() as session:
        assert await CourseRepository(session).list_by_user(user_b) == []
        assert await NoteRepository(session).list_by_user(user_b) == []
        assert (
            await ReminderRepository(session).list_by_user(user_b, active_only=False)
            == []
        )
        assert await CalendarEventRepository(session).list_by_user(user_b) == []
        assert await LinkRepository(session).list_by_user(user_b) == []
        assert await UserRepository(session).get_by_telegram_id(USER_A)


# --- conversation guards -------------------------------------------------
async def test_wizard_cancel_buttons_reach_a_handler(db):
    """Every ``❌ لغو`` button must map to a registered callback handler."""
    for module, data in (
        (grades_module, "grades:cancel"),
        (courses_module, "course:cancel"),
    ):
        conversation = module.build_conversation()
        handlers = [
            handler
            for state_handlers in conversation.states.values()
            for handler in state_handlers
        ] + list(conversation.fallbacks or [])
        assert any(
            isinstance(handler, CallbackQueryHandler)
            and handler.pattern is not None
            and handler.pattern.match(data)
            for handler in handlers
        ), f"{data} has no registered handler"

    # the same for the sections that already had one
    for conversation, data in (
        (calendar_conv(), "cal:cancel"),
        (calendar_conv(), "cal:skip"),
    ):
        handlers = [
            handler
            for state_handlers in conversation.states.values()
            for handler in state_handlers
        ] + list(conversation.fallbacks or [])
        assert any(
            isinstance(handler, CallbackQueryHandler)
            and handler.pattern is not None
            and handler.pattern.match(data)
            for handler in handlers
        ), f"{data} has no registered handler"


async def test_grades_cancel_button_clears_the_wizard_state(db):
    ctx = await _register(USER_A)
    course_id = await _course_for(ctx)

    await grade_add(
        make_callback_update(f"grades:add:{course_id}", user_id=USER_A), ctx
    )
    assert "grade_wizard" in ctx.user_data

    state = await grades_module.cancel_conversation(
        make_callback_update("grades:cancel", user_id=USER_A), ctx
    )

    assert state == ConversationHandler.END
    assert "grade_wizard" not in ctx.user_data
    assert "grade_course_id" not in ctx.user_data
    assert "grade_item_id" not in ctx.user_data


async def test_schedule_is_never_shared_between_students(db):
    """The weekly-schedule query is per user: A's photo stays A's."""
    ctx_a = await _register(USER_A)
    ctx_b = await _register(USER_B)
    user_a = ctx_a.user_data["user_id"]
    user_b = ctx_b.user_data["user_id"]

    await _save_schedule(user_a, "A-ONLY-FILE")

    async with get_session() as session:
        assert (
            await WeeklyScheduleRepository(session).get_active(user_b)
        ) is None
        schedule_a = await WeeklyScheduleRepository(session).get_active(user_a)
    assert schedule_a is not None
    assert schedule_a.telegram_file_id == "A-ONLY-FILE"


async def _save_schedule(user_id: int, file_id: str) -> None:
    """Small helper: store one active schedule for a given internal user id."""
    async with get_session() as session:
        await WeeklyScheduleRepository(session).save(
            user_id=user_id, telegram_file_id=file_id, file_unique_id=None
        )
