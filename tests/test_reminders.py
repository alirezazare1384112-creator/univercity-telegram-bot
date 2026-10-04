"""⏰ یادآوری‌ها tests: wizard, delivery service and repetition."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.bot.handlers.reminders import (
    build_conversation,
    on_add_clicked,
    on_alert_save,
    on_alert_toggle,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_edit_clicked,
    on_open,
    on_pause_clicked,
    on_single_choice,
    on_skip_clicked,
    on_wizard_text,
    reminders_menu,
)
from app.bot.keyboards.main_menu import REMINDERS
from app.bot.middlewares import capture_user
from app.bot.states.reminder_states import ReminderState
from app.database.database import get_session
from app.database.models.notification import STATUS_FAILED, STATUS_SENT, TYPE_REMINDER
from app.database.models.reminder import ALERT_AT_TIME, ALERT_HOURS_1, REPEAT_DAILY
from app.database.repositories import (
    NotificationLogRepository,
    ReminderNotificationRepository,
    ReminderRepository,
    UserRepository,
)
from app.database.repositories.reminder_repository import fire_datetimes, next_occurrence
from app.scheduler import run_one_cycle, start_scheduler, stop_scheduler
from app.services.reminder_service import process_due_notifications, sync_notifications
from app.utils.datetime_utils import utcnow_naive
from tests.helpers import FakeContext, make_callback_update, make_text_update

TZ = "Asia/Tehran"


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _create_reminder(
    context: FakeContext,
    telegram_id: int,
    *,
    title: str = "تحویل پروژه",
    when: str = "فردا ساعت 18:30",
    repeat: str = REPEAT_DAILY,
) -> int:
    """Drive the whole creation wizard and return the new reminder's id."""
    user_id = context.user_data.get("user_id")
    async with get_session() as session:
        known_ids = {r.id for r in await ReminderRepository(session).list_by_user(user_id, active_only=False)}

    await reminders_menu(make_text_update(REMINDERS, user_id=telegram_id), context)
    await on_add_clicked(make_callback_update("rem:add", user_id=telegram_id), context)
    await on_wizard_text(make_text_update(title, user_id=telegram_id), context)
    await on_wizard_text(make_text_update(when, user_id=telegram_id), context)
    await on_single_choice(
        make_callback_update("rem:course:none", user_id=telegram_id), context
    )
    await on_single_choice(
        make_callback_update(f"rem:repeat:{repeat}", user_id=telegram_id), context
    )
    await on_skip_clicked(make_callback_update("rem:skip", user_id=telegram_id), context)
    await on_alert_save(
        make_callback_update("rem:alert:save", user_id=telegram_id), context
    )

    async with get_session() as session:
        reminders = await ReminderRepository(session).list_by_user(user_id, active_only=False)
    created = [reminder for reminder in reminders if reminder.id not in known_ids]
    assert len(created) == 1
    return created[0].id


async def _seed(
    telegram_id: int,
    *,
    when,
    repeat: str = "NONE",
    fire=None,
    active: bool = True,
    title: str = "جلسه دفاع",
):
    """Insert a reminder straight into the database (service tests)."""
    async with get_session() as session:
        user = await UserRepository(session).upsert_from_telegram(
            telegram_id=telegram_id, username="t", first_name="T", last_name=None
        )
        reminder = await ReminderRepository(session).create(
            user_id=user.id,
            title=title,
            reminder_datetime=when,
            repeat_type=repeat,
            is_active=active,
        )
        await ReminderNotificationRepository(session).create(
            reminder_id=reminder.id,
            alert_offset=ALERT_AT_TIME,
            fire_datetime=fire if fire is not None else when,
        )
    return user, reminder


# --- wizard -------------------------------------------------------------
async def test_empty_list_invites_the_student(db):
    context = await _register(6001)

    state = await reminders_menu(make_text_update(REMINDERS, user_id=6001), context)

    assert state == ReminderState.LIST
    assert "هنوز یادآوری‌ای نساخته‌ای" in context.sent_texts[-1]
    assert "➕ یادآوری جدید" in str(context.last_markup)


async def test_full_creation_wizard(db):
    context = await _register(6002)
    await _create_reminder(context, 6002, title="پروژه پایگاه داده")

    assert any("✅ یادآوری ساخته شد" in text for text in context.sent_texts)
    assert "📌 عنوان: پروژه پایگاه داده" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        reminder = (await ReminderRepository(session).list_by_user(user_id, active_only=False))[0]
        notifications = await ReminderNotificationRepository(session).list_for_reminder(
            reminder.id
        )

    assert reminder.course_id is None  # skipped
    assert reminder.description is None  # skipped
    assert reminder.repeat_type == REPEAT_DAILY
    assert reminder.is_active is True
    # one pending alert, exactly at the reminder moment
    assert len(notifications) == 1
    assert notifications[0].alert_offset == ALERT_AT_TIME
    assert notifications[0].fire_datetime == reminder.reminder_datetime
    assert notifications[0].is_sent is False


async def test_invalid_datetime_keeps_the_wizard_open(db):
    context = await _register(6003)
    await reminders_menu(make_text_update(REMINDERS, user_id=6003), context)
    await on_add_clicked(make_callback_update("rem:add", user_id=6003), context)
    await on_wizard_text(make_text_update("جلسه", user_id=6003), context)

    state = await on_wizard_text(make_text_update("هر وقت", user_id=6003), context)

    assert state == ReminderState.WIZARD
    assert "⚠️" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await ReminderRepository(session).list_by_user(user_id, active_only=False) == []


async def test_past_datetime_is_rejected(db):
    context = await _register(6004)
    await reminders_menu(make_text_update(REMINDERS, user_id=6004), context)
    await on_add_clicked(make_callback_update("rem:add", user_id=6004), context)
    await on_wizard_text(make_text_update("جلسه", user_id=6004), context)

    state = await on_wizard_text(
        make_text_update("ديروز ساعت 10:00", user_id=6004), context
    )

    assert state == ReminderState.WIZARD
    assert "آینده" in context.sent_texts[-1]


async def test_list_shows_every_reminder(db):
    context = await _register(6005)
    await _create_reminder(context, 6005, title="میان‌ترم")
    await _create_reminder(context, 6005, title="کوئیز", when="پس فردا ساعت 9")

    context.bot.send_message.reset_mock()
    state = await reminders_menu(make_text_update(REMINDERS, user_id=6005), context)

    assert state == ReminderState.LIST
    assert "میان‌ترم" in context.sent_texts[-1]
    assert "کوئیز" in context.sent_texts[-1]


# --- edit / pause / delete ----------------------------------------------
async def test_edit_datetime(db):
    context = await _register(6006)
    reminder_id = await _create_reminder(context, 6006)

    state = await on_edit_clicked(
        make_callback_update(f"rem:edit:{reminder_id}:datetime", user_id=6006), context
    )
    assert state == ReminderState.WIZARD
    assert "زمان یادآوری" in context.sent_texts[-1]

    old = context.user_data["user_id"]
    async with get_session() as session:
        before = await ReminderRepository(session).get(reminder_id, old)

    state = await on_wizard_text(
        make_text_update("پس فردا ساعت 9", user_id=6006), context
    )
    assert state == ReminderState.DETAIL
    assert any("✅ تغییرات ذخیره شد" in text for text in context.sent_texts)

    async with get_session() as session:
        after = await ReminderRepository(session).get(reminder_id, old)
        notifications = await ReminderNotificationRepository(session).list_for_reminder(
            reminder_id
        )

    assert after.reminder_datetime != before.reminder_datetime
    assert after.title == before.title  # untouched field
    assert after.repeat_type == before.repeat_type  # untouched field
    # the pending alert follows the new moment
    assert notifications[0].fire_datetime == after.reminder_datetime


async def test_edit_title_keeps_the_selected_alerts(db):
    context = await _register(6007)
    reminder_id = await _create_reminder(context, 6007)

    await on_edit_clicked(
        make_callback_update(f"rem:edit:{reminder_id}:alerts", user_id=6007), context
    )
    await on_alert_toggle(
        make_callback_update(f"rem:alert:{ALERT_HOURS_1}", user_id=6007), context
    )
    await on_alert_save(make_callback_update("rem:alert:save", user_id=6007), context)

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        offsets = {
            n.alert_offset
            for n in await ReminderNotificationRepository(session).list_for_reminder(
                reminder_id
            )
        }
    assert offsets == {ALERT_AT_TIME, ALERT_HOURS_1}

    # editing the title must not throw the extra alert away
    await on_edit_clicked(
        make_callback_update(f"rem:edit:{reminder_id}:title", user_id=6007), context
    )
    await on_wizard_text(make_text_update("عنوان تازه", user_id=6007), context)

    async with get_session() as session:
        offsets = {
            n.alert_offset
            for n in await ReminderNotificationRepository(session).list_for_reminder(
                reminder_id
            )
        }
        reminder = await ReminderRepository(session).get(reminder_id, user_id)
    assert offsets == {ALERT_AT_TIME, ALERT_HOURS_1}
    assert reminder.title == "عنوان تازه"


async def test_pause_and_resume(db):
    context = await _register(6008)
    reminder_id = await _create_reminder(context, 6008)

    state = await on_pause_clicked(
        make_callback_update(f"rem:pause:{reminder_id}", user_id=6008), context
    )
    assert state == ReminderState.DETAIL
    assert any("غیرفعال شد" in text for text in context.sent_texts)

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        reminder = await ReminderRepository(session).get(reminder_id, user_id)
    assert reminder.is_active is False
    assert "متوقف" in context.sent_texts[-1]

    await on_pause_clicked(
        make_callback_update(f"rem:pause:{reminder_id}", user_id=6008), context
    )
    async with get_session() as session:
        reminder = await ReminderRepository(session).get(reminder_id, user_id)
    assert reminder.is_active is True
    assert any("فعال شد" in text for text in context.sent_texts)


async def test_delete_requires_confirmation(db):
    context = await _register(6009)
    reminder_id = await _create_reminder(context, 6009)

    state = await on_delete_clicked(
        make_callback_update(f"rem:delete:{reminder_id}", user_id=6009), context
    )
    assert state == ReminderState.DETAIL
    assert "حذف شود" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    await on_delete_cancelled(
        make_callback_update("rem:delete:no", user_id=6009), context
    )
    async with get_session() as session:
        assert await ReminderRepository(session).get(reminder_id, user_id) is not None

    await on_delete_clicked(
        make_callback_update(f"rem:delete:{reminder_id}", user_id=6009), context
    )
    state = await on_delete_confirmed(
        make_callback_update(f"rem:delete:{reminder_id}:yes", user_id=6009), context
    )
    assert state == ReminderState.LIST
    async with get_session() as session:
        assert await ReminderRepository(session).get(reminder_id, user_id) is None
        assert await ReminderNotificationRepository(session).list_for_reminder(
            reminder_id
        ) == []


async def test_one_student_cannot_open_another_students_reminder(db):
    context_a = await _register(6010)
    reminder_id = await _create_reminder(context_a, 6010, title="محرمانه")

    context_b = await _register(6011)
    state = await on_open(
        make_callback_update(f"rem:open:{reminder_id}", user_id=6011), context_b
    )

    assert state == ReminderState.LIST
    assert any("پیدا نشد" in text for text in context_b.sent_texts)
    assert "محرمانه" not in "\n".join(context_b.sent_texts)


def test_conversation_covers_the_three_states():
    handler = build_conversation()
    assert set(handler.states) == {
        ReminderState.LIST,
        ReminderState.DETAIL,
        ReminderState.WIZARD,
    }


# --- delivery service ----------------------------------------------------
async def test_due_alert_is_delivered_and_logged(db):
    past = utcnow_naive() - timedelta(minutes=5)
    user, reminder = await _seed(6012, when=past)
    sent: list[tuple[int, str]] = []

    async def send_message(*, chat_id: int, text: str) -> None:
        sent.append((chat_id, text))

    counters = await process_due_notifications(send_message, TZ)

    assert counters == {"sent": 1, "failed": 0, "advanced": 0}
    assert sent[0][0] == user.telegram_id
    assert "جلسه دفاع" in sent[0][1]

    async with get_session() as session:
        notifications = await ReminderNotificationRepository(session).list_for_reminder(
            reminder.id
        )
        assert notifications[0].is_sent is True
        assert notifications[0].sent_at is not None
        logs = await NotificationLogRepository(session).recent()
        assert len(logs) == 1
        assert logs[0].status == STATUS_SENT
        assert logs[0].notification_type == TYPE_REMINDER
        assert logs[0].related_id == reminder.id


async def test_failed_delivery_is_recorded_and_not_retried(db):
    past = utcnow_naive() - timedelta(minutes=5)
    _, reminder = await _seed(6013, when=past)

    async def send_message(**_kwargs) -> None:
        raise RuntimeError("telegram is down")

    counters = await process_due_notifications(send_message, TZ)

    assert counters == {"sent": 0, "failed": 1, "advanced": 0}

    async with get_session() as session:
        notifications = await ReminderNotificationRepository(session).list_for_reminder(
            reminder.id
        )
        assert notifications[0].is_sent is True  # no endless retry loop
        logs = await NotificationLogRepository(session).recent()
        assert logs[0].status == STATUS_FAILED
        assert logs[0].error_message == "RuntimeError"


async def test_future_and_paused_alerts_are_not_sent(db):
    now = utcnow_naive()
    await _seed(6014, when=now + timedelta(hours=3))  # not due yet
    await _seed(6015, when=now - timedelta(hours=3), active=False)  # paused

    async def send_message(**_kwargs) -> None:  # pragma: no cover - must not run
        raise AssertionError("nothing should be sent")

    counters = await process_due_notifications(send_message, TZ)

    assert counters == {"sent": 0, "failed": 0, "advanced": 0}
    async with get_session() as session:
        assert await NotificationLogRepository(session).recent() == []


async def test_repeating_reminder_advances_and_gets_new_alerts(db):
    now = utcnow_naive()
    user, reminder = await _seed(6016, when=now - timedelta(days=2), repeat=REPEAT_DAILY)
    sent: list[str] = []

    async def send_message(*, chat_id: int, text: str) -> None:
        sent.append(text)

    counters = await process_due_notifications(send_message, TZ)

    assert counters["sent"] == 1
    assert counters["advanced"] == 1

    async with get_session() as session:
        stored = await ReminderRepository(session).get(reminder.id, user.id)
        notifications = await ReminderNotificationRepository(session).list_for_reminder(
            reminder.id
        )

    assert stored.reminder_datetime > now  # moved to the next occurrence
    assert len(notifications) == 1
    assert notifications[0].is_sent is False
    assert notifications[0].fire_datetime == stored.reminder_datetime


async def test_edit_regenerates_only_future_alerts(db):
    now = utcnow_naive()
    _, reminder = await _seed(6017, when=now + timedelta(hours=6))

    async with get_session() as session:
        created = await sync_notifications(
            session, reminder, [ALERT_AT_TIME, ALERT_HOURS_1]
        )
        offsets = {
            n.alert_offset
            for n in await ReminderNotificationRepository(session).list_for_reminder(
                reminder.id
            )
        }

    assert created == 2
    assert offsets == {ALERT_AT_TIME, ALERT_HOURS_1}


# --- pure helpers --------------------------------------------------------
def test_next_occurrence_is_calendar_safe():
    assert next_occurrence(datetime(2026, 12, 15, 10, 0), "MONTHLY") == datetime(
        2027, 1, 15, 10, 0
    )
    assert next_occurrence(datetime(2026, 1, 31, 10, 0), "MONTHLY") == datetime(
        2026, 2, 28, 10, 0
    )
    assert next_occurrence(datetime(2026, 1, 1, 8, 0), "DAILY") == datetime(
        2026, 1, 2, 8, 0
    )
    assert next_occurrence(datetime(2026, 1, 1, 8, 0), "NONE") == datetime(2026, 1, 1, 8, 0)


def test_fire_datetimes_subtract_the_alert_offsets():
    moment = datetime(2026, 10, 5, 15, 0)
    pairs = dict(fire_datetimes(moment, [ALERT_AT_TIME, ALERT_HOURS_1]))

    assert pairs[ALERT_AT_TIME] == moment
    assert pairs[ALERT_HOURS_1] == moment - timedelta(hours=1)


# --- database poller (app.scheduler) ------------------------------------
def _fake_application():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    return SimpleNamespace(bot=AsyncMock(), bot_data={})


async def test_scheduler_cycle_delivers_through_the_bot(db):
    past = utcnow_naive() - timedelta(minutes=2)
    user, _reminder = await _seed(6018, when=past)
    application = _fake_application()

    counters = await run_one_cycle(application)

    assert counters["sent"] == 1
    application.bot.send_message.assert_awaited_once()
    kwargs = application.bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == user.telegram_id
    assert "جلسه دفاع" in kwargs["text"]


async def test_scheduler_starts_a_task_and_stops_it(db):
    application = _fake_application()

    await start_scheduler(application)
    task = application.bot_data.get("reminder_poller_task")
    assert task is not None and not task.done()

    await stop_scheduler(application)
    assert task.done()
    assert "reminder_poller_task" not in application.bot_data
