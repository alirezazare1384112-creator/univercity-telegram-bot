"""End-to-end acceptance test.

One student walks through every feature using the real handlers, a second
student is checked to be fully isolated from that data, the admin panel is
exercised, and finally the "bot process" is restarted to prove that data and
pending reminders survive.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram.ext import ConversationHandler

from app.bot.handlers.admin import cmd_admin
from app.bot.handlers.announcements import announcements_menu
from app.bot.handlers.announcements import on_add_clicked as ann_add
from app.bot.handlers.announcements import on_post_text as ann_post
from app.bot.handlers.calendar_events import calendar_menu
from app.bot.handlers.calendar_events import on_add_clicked as cal_add
from app.bot.handlers.calendar_events import on_wizard_text as cal_text
from app.bot.handlers.courses import courses_menu
from app.bot.handlers.courses import on_add_clicked as course_add
from app.bot.handlers.courses import on_open_course as course_open
from app.bot.handlers.courses import on_skip_clicked as course_skip
from app.bot.handlers.courses import on_wizard_text as course_text
from app.bot.handlers.gpa import gpa_handler
from app.bot.handlers.grades import grades_menu, on_pick_course
from app.bot.handlers.grades import on_add_clicked as grade_add
from app.bot.handlers.grades import on_skip_clicked as grade_skip
from app.bot.handlers.grades import on_wizard_text as grade_text
from app.bot.handlers.links import links_menu
from app.bot.handlers.links import on_add_clicked as link_add
from app.bot.handlers.links import on_open as link_open
from app.bot.handlers.links import on_skip_clicked as link_skip
from app.bot.handlers.links import on_wizard_text as link_text
from app.bot.handlers.notes import notes_menu
from app.bot.handlers.notes import on_add_clicked as note_add
from app.bot.handlers.notes import on_course_chosen as note_course
from app.bot.handlers.notes import on_file_received as note_file
from app.bot.handlers.notes import on_open as note_open
from app.bot.handlers.notes import on_skip_clicked as note_skip
from app.bot.handlers.notes import on_wizard_text as note_text
from app.bot.handlers.reminders import on_add_clicked as rem_add
from app.bot.handlers.reminders import on_alert_save as rem_alert_save
from app.bot.handlers.reminders import on_single_choice as rem_choice
from app.bot.handlers.reminders import on_skip_clicked as rem_skip
from app.bot.handlers.reminders import on_wizard_text as rem_text
from app.bot.handlers.reminders import reminders_menu
from app.bot.handlers.schedule import on_add_clicked as sched_add
from app.bot.handlers.schedule import on_photo_received, schedule_menu
from app.bot.handlers.start import cmd_start
from app.bot.keyboards.main_menu import (
    ANNOUNCEMENTS,
    CALENDAR,
    COURSES,
    GPA,
    GRADES,
    LINKS,
    NOTES,
    REMINDERS,
    SCHEDULE,
)
from app.bot.middlewares import capture_user
from app.database.database import build_engine, get_session
from app.database.models import Base
from app.database.repositories import (
    AdminRepository,
    AnnouncementRepository,
    CalendarEventRepository,
    CourseRepository,
    GradeItemRepository,
    LinkRepository,
    NoteRepository,
    NotificationLogRepository,
    ReminderNotificationRepository,
    ReminderRepository,
    WeeklyScheduleRepository,
)
from app.scheduler import run_one_cycle
from app.utils.datetime_utils import utcnow_naive
from tests.helpers import FakeContext, make_callback_update, make_photo_update, make_text_update

STUDENT_A = 9601
STUDENT_B = 9602
ADMIN_ID = 9603


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


def _all_texts(ctx: FakeContext) -> list[str]:
    """Everything the bot sent as text: messages *and* file captions."""
    texts = list(ctx.sent_texts)
    for method in (ctx.bot.send_photo, ctx.bot.send_document):
        for call in method.call_args_list:
            caption = call.kwargs.get("caption")
            if caption:
                texts.append(caption)
    return texts


# --- one helper per feature (drives the real wizard end to end) ----------
async def _add_course(ctx: FakeContext, tg: int, name: str = "پایگاه داده") -> int:
    user_id = ctx.user_data["user_id"]
    await courses_menu(make_text_update(COURSES, user_id=tg), ctx)
    await course_add(make_callback_update("course:add", user_id=tg), ctx)
    await course_text(make_text_update(name, user_id=tg), ctx)
    await course_text(make_text_update("3", user_id=tg), ctx)
    for _ in range(3):  # teacher / semester / academic year
        await course_skip(make_callback_update("course:skip", user_id=tg), ctx)
    async with get_session() as session:
        return (await CourseRepository(session).list_by_user(user_id))[0].id


async def _add_grade(ctx: FakeContext, tg: int, course_id: int) -> None:
    await grades_menu(make_text_update(GRADES, user_id=tg), ctx)
    await on_pick_course(
        make_callback_update(f"grades:course:{course_id}", user_id=tg), ctx
    )
    await grade_add(make_callback_update(f"grades:add:{course_id}", user_id=tg), ctx)
    await grade_text(make_text_update("میان‌ترم", user_id=tg), ctx)
    await grade_text(make_text_update("20", user_id=tg), ctx)
    await grade_text(make_text_update("16", user_id=tg), ctx)
    await grade_skip(make_callback_update("grades:skip", user_id=tg), ctx)


async def _upload_schedule(ctx: FakeContext, tg: int) -> None:
    await schedule_menu(make_text_update(SCHEDULE, user_id=tg), ctx)
    await sched_add(make_callback_update("schedule:add", user_id=tg), ctx)
    await on_photo_received(make_photo_update(file_id="SCHED-A", user_id=tg), ctx)


async def _add_reminder(ctx: FakeContext, tg: int, when: str = "فردا ساعت 18:30") -> int:
    user_id = ctx.user_data["user_id"]
    await reminders_menu(make_text_update(REMINDERS, user_id=tg), ctx)
    await rem_add(make_callback_update("rem:add", user_id=tg), ctx)
    await rem_text(make_text_update("تحویل پروژه", user_id=tg), ctx)
    await rem_text(make_text_update(when, user_id=tg), ctx)
    await rem_choice(make_callback_update("rem:course:none", user_id=tg), ctx)
    await rem_choice(make_callback_update("rem:repeat:DAILY", user_id=tg), ctx)
    await rem_skip(make_callback_update("rem:skip", user_id=tg), ctx)
    await rem_alert_save(make_callback_update("rem:alert:save", user_id=tg), ctx)
    async with get_session() as session:
        reminders = await ReminderRepository(session).list_by_user(
            user_id, active_only=False
        )
        return reminders[0].id


async def _add_event(ctx: FakeContext, tg: int) -> None:
    await calendar_menu(make_text_update(CALENDAR, user_id=tg), ctx)
    await cal_add(make_callback_update("cal:add", user_id=tg), ctx)
    await cal_text(make_text_update("امتحان پایگاه داده", user_id=tg), ctx)
    await cal_text(make_text_update("فردا", user_id=tg), ctx)
    await cal_text(make_text_update("18:30", user_id=tg), ctx)
    await cal_text(make_text_update("سالن ۳", user_id=tg), ctx)


async def _add_note(ctx: FakeContext, tg: int, course_id: int) -> int:
    user_id = ctx.user_data["user_id"]
    await notes_menu(make_text_update(NOTES, user_id=tg), ctx)
    await note_add(make_callback_update("note:add", user_id=tg), ctx)
    await note_text(make_text_update("فصل ۳ نرمال‌سازی", user_id=tg), ctx)
    await note_file(make_photo_update(file_id="NOTE-A", user_id=tg), ctx)
    await note_course(make_callback_update(f"note:course:{course_id}", user_id=tg), ctx)
    await note_skip(make_callback_update("note:skip", user_id=tg), ctx)
    async with get_session() as session:
        return (await NoteRepository(session).list_by_user(user_id))[0].id


async def _add_link(ctx: FakeContext, tg: int) -> int:
    user_id = ctx.user_data["user_id"]
    await links_menu(make_text_update(LINKS, user_id=tg), ctx)
    await link_add(make_callback_update("link:add", user_id=tg), ctx)
    await link_text(make_text_update("آموزش یکپارچه", user_id=tg), ctx)
    await link_text(make_text_update("portal.university.ir", user_id=tg), ctx)
    await link_skip(make_callback_update("link:skip", user_id=tg), ctx)
    async with get_session() as session:
        return (await LinkRepository(session).list_by_user(user_id))[0].id


async def _save_announcement(ctx: FakeContext, tg: int) -> int:
    user_id = ctx.user_data["user_id"]
    await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=tg), ctx)
    await ann_add(make_callback_update("ann:add", user_id=tg), ctx)
    await ann_post(make_text_update("برنامه امتحانات\nجزئیات در وب‌سایت", user_id=tg), ctx)
    async with get_session() as session:
        return (await AnnouncementRepository(session).list_by_user(user_id))[0].id


# --- 1) the whole journey -----------------------------------------------
async def test_full_student_journey(db):
    ctx = await _register(STUDENT_A)
    user_id = ctx.user_data["user_id"]

    # /start greets the student and shows the persistent main menu
    await cmd_start(make_text_update("/start", user_id=STUDENT_A), ctx)
    assert any("دستیار دانشجو" in text for text in ctx.sent_texts)
    assert ctx.last_markup is not None

    course_id = await _add_course(ctx, STUDENT_A)
    await _add_grade(ctx, STUDENT_A, course_id)
    await _upload_schedule(ctx, STUDENT_A)
    await _add_reminder(ctx, STUDENT_A)
    await _add_event(ctx, STUDENT_A)
    note_id = await _add_note(ctx, STUDENT_A, course_id)
    link_id = await _add_link(ctx, STUDENT_A)
    await _save_announcement(ctx, STUDENT_A)
    await gpa_handler(make_text_update(GPA, user_id=STUDENT_A), ctx)

    async with get_session() as session:
        assert await CourseRepository(session).count(user_id) == 1
        assert await GradeItemRepository(session).count(course_id) == 1
        assert await WeeklyScheduleRepository(session).count(user_id) == 1
        assert await ReminderRepository(session).count(user_id) == 1
        assert await CalendarEventRepository(session).count(user_id) == 1
        assert await NoteRepository(session).count(user_id) == 1
        assert await LinkRepository(session).count(user_id) == 1
        assert await AnnouncementRepository(session).count(user_id) == 1
        note = await NoteRepository(session).get(note_id, user_id)
        schedule = await WeeklyScheduleRepository(session).get_active(user_id)

    assert note is not None and note.course_id == course_id
    assert schedule is not None and schedule.telegram_file_id == "SCHED-A"

    # the GPA step opened the configured website
    url_buttons = [
        button
        for message in ctx.sent_messages
        for row in getattr(message.get("reply_markup"), "inline_keyboard", []) or []
        for button in row
        if button.url
    ]
    assert url_buttons, "the GPA step must offer a URL button"

    # re-open a saved item through its own button
    ctx.bot.send_message.reset_mock()
    await note_open(make_callback_update(f"note:open:{note_id}", user_id=STUDENT_A), ctx)
    assert any("فصل ۳" in text for text in _all_texts(ctx))
    await link_open(make_callback_update(f"link:open:{link_id}", user_id=STUDENT_A), ctx)
    assert any("آموزش یکپارچه" in text for text in _all_texts(ctx))
    await course_open(
        make_callback_update(f"course:open:{course_id}", user_id=STUDENT_A), ctx
    )
    assert any("پایگاه داده" in text for text in _all_texts(ctx))


# --- 2) isolation --------------------------------------------------------
async def test_second_student_cannot_see_the_first_students_data(db):
    ctx_a = await _register(STUDENT_A)
    ctx_b = await _register(STUDENT_B)
    user_b = ctx_b.user_data["user_id"]

    course_id = await _add_course(ctx_a, STUDENT_A)
    await _add_grade(ctx_a, STUDENT_A, course_id)
    await _upload_schedule(ctx_a, STUDENT_A)
    reminder_id = await _add_reminder(ctx_a, STUDENT_A)
    note_id = await _add_note(ctx_a, STUDENT_A, course_id)

    # B's own views are empty
    await courses_menu(make_text_update(COURSES, user_id=STUDENT_B), ctx_b)
    assert "هنوز" in ctx_b.sent_texts[-1] or "درسی" in ctx_b.sent_texts[-1]
    await notes_menu(make_text_update(NOTES, user_id=STUDENT_B), ctx_b)
    assert "هنوز" in ctx_b.sent_texts[-1]

    async with get_session() as session:
        assert await CourseRepository(session).count(user_b) == 0
        assert await NoteRepository(session).count(user_b) == 0
        assert await ReminderRepository(session).count(user_b) == 0
        assert await WeeklyScheduleRepository(session).get_active(user_b) is None

    # and B cannot reach A's rows by id
    ctx_b.bot.send_message.reset_mock()
    await note_open(
        make_callback_update(f"note:open:{note_id}", user_id=STUDENT_B), ctx_b
    )
    assert any("پیدا نشد" in text for text in ctx_b.sent_texts)

    await reminders_menu(make_text_update(REMINDERS, user_id=STUDENT_B), ctx_b)
    assert any("هنوز" in text for text in ctx_b.sent_texts)
    assert reminder_id  # A's reminder exists but is invisible to B


# --- 3) admin ------------------------------------------------------------
async def test_admin_panel_is_protected_and_works(db):
    ctx_admin = await _register(ADMIN_ID)
    ctx_student = await _register(STUDENT_B)

    # a normal student cannot open the panel
    assert await cmd_admin(make_text_update("/admin", user_id=STUDENT_B), ctx_student) is None

    async with get_session() as session:
        await AdminRepository(session).upsert(
            telegram_id=ADMIN_ID, username="boss", first_name="Boss"
        )

    state = await cmd_admin(make_text_update("/admin", user_id=ADMIN_ID), ctx_admin)
    assert state is not None
    assert state != ConversationHandler.END


# --- 4) restart ----------------------------------------------------------
async def test_data_and_pending_reminders_survive_a_restart(tmp_path, monkeypatch):
    """Stop the "process", start a new one, and check nothing was lost."""
    import app.database.database as db_module

    url = f"sqlite+aiosqlite:///{(tmp_path / 'restart.db').as_posix()}"

    async def _start_process():
        """One bot process: brand new engine + session factory."""
        engine = build_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        monkeypatch.setattr(db_module, "_engine", engine)
        monkeypatch.setattr(db_module, "_session_factory", factory)
        return engine

    # --- first run -------------------------------------------------------
    await _start_process()
    ctx = await _register(STUDENT_A)
    user_id = ctx.user_data["user_id"]
    course_id = await _add_course(ctx, STUDENT_A)
    reminder_id = await _add_reminder(ctx, STUDENT_A)

    # make the alert due while the bot is "down"
    due = utcnow_naive() - timedelta(hours=2)
    async with get_session() as session:
        reminder = await ReminderRepository(session).get(reminder_id, user_id)
        reminder.reminder_datetime = due
        for notification in await ReminderNotificationRepository(session).list_for_reminder(
            reminder_id
        ):
            notification.fire_datetime = due

    await db_module.dispose_engine()  # <- bot stopped

    # --- second run: same database file ----------------------------------
    await _start_process()
    ctx2 = FakeContext()
    await capture_user(make_text_update("/start", user_id=STUDENT_A), ctx2)

    assert ctx2.user_data["is_new_user"] is False  # the row survived
    async with get_session() as session:
        assert await CourseRepository(session).count(user_id) == 1
        assert await ReminderRepository(session).count(user_id) == 1
        assert await GradeItemRepository(session).count(course_id) == 0

    # the overdue alert is delivered exactly once after the restart
    class _App:  # minimal stand-in: run_one_cycle only needs .bot.send_message
        def __init__(self, bot) -> None:
            self.bot = bot

    counters = await run_one_cycle(_App(ctx2.bot))
    assert counters["sent"] == 1

    counters_again = await run_one_cycle(_App(ctx2.bot))
    assert counters_again["sent"] == 0  # never sent twice

    async with get_session() as session:
        logs = await NotificationLogRepository(session).recent(limit=10)
    assert any(log.status == "SENT" for log in logs)

    await db_module.dispose_engine()
