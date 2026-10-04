"""Reminder service: alert generation and delivery.

The service never holds two database sessions at the same time:

1. ``collect_due`` reads what must be sent now (session 1, then closed)
2. messages are sent with no session open
3. results are written back (session 2)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_session
from app.database.models import Reminder
from app.database.models.notification import STATUS_FAILED, STATUS_SENT, TYPE_REMINDER
from app.database.models.reminder import ALERT_DAYS_1, ALERT_HOURS_1
from app.database.repositories import NotificationLogRepository
from app.database.repositories.reminder_repository import (
    ReminderNotificationRepository,
    fire_datetimes,
    next_occurrence,
)
from app.utils.datetime_utils import format_jalali, utcnow_naive

logger = logging.getLogger(__name__)

ALERT_PREFIX = {
    "AT_TIME": "⏰ وقت یادآوری رسید:",
    ALERT_HOURS_1: "⏱ ۱ ساعت دیگر:",
    ALERT_DAYS_1: "📆 فردا همین وقت:",
}


@dataclass(slots=True)
class DueAlert:
    """Plain copy of a due notification (safe to use after the session)."""

    notification_id: int
    alert_offset: str
    reminder_id: int
    reminder_datetime: datetime
    title: str
    description: str | None
    repeat_type: str
    user_id: int
    telegram_id: int


def build_alert_message(alert: DueAlert, timezone_name: str) -> str:
    prefix = ALERT_PREFIX.get(alert.alert_offset, "⏰ یادآوری:")
    lines = [f"{prefix} {alert.title}"]
    lines.append(f"🕒 {format_jalali(alert.reminder_datetime, timezone_name)}")
    if alert.description:
        lines.append(f"📝 {alert.description}")
    return "\n".join(lines)


async def sync_notifications(
    session: AsyncSession,
    reminder: Reminder,
    alert_offsets: list[str] | tuple[str, ...],
    now: datetime | None = None,
) -> int:
    """Rebuild the pending alerts of one reminder.

    Called after create/edit/pause. Already sent alerts of the current
    occurrence are kept, only future ones are regenerated.
    """
    current = now or utcnow_naive()
    repo = ReminderNotificationRepository(session)

    # drop everything that has not been sent yet
    for notification in await repo.pending_for_reminder(reminder.id):
        await session.delete(notification)
    await session.flush()

    created = 0
    for offset, fire_at in fire_datetimes(reminder.reminder_datetime, alert_offsets):
        if fire_at <= current:  # the alert would be in the past
            continue
        await repo.create(
            reminder_id=reminder.id, alert_offset=offset, fire_datetime=fire_at
        )
        created += 1
    return created


async def alert_offsets_of(session: AsyncSession, reminder_id: int) -> list[str]:
    """Offsets currently configured for a reminder (for the edit screen)."""
    repo = ReminderNotificationRepository(session)
    notifications = await repo.list_for_reminder(reminder_id)
    offsets = {notification.alert_offset for notification in notifications}
    # a fully delivered occurrence leaves no row: fall back to AT_TIME
    return sorted(offsets) or ["AT_TIME"]


async def collect_due(
    session: AsyncSession, now: datetime | None = None, limit: int = 50
) -> list[DueAlert]:
    current = now or utcnow_naive()
    repo = ReminderNotificationRepository(session)
    rows = await repo.due(current, limit=limit)
    return [
        DueAlert(
            notification_id=notification.id,
            alert_offset=notification.alert_offset,
            reminder_id=reminder.id,
            reminder_datetime=reminder.reminder_datetime,
            title=reminder.title,
            description=reminder.description,
            repeat_type=reminder.repeat_type,
            user_id=reminder.user_id,
            telegram_id=user.telegram_id,
        )
        for notification, reminder, user in rows
    ]


async def advance_repeating(session: AsyncSession, now: datetime | None = None) -> int:
    """Move every overdue repeating reminder to its next occurrence.

    The alert offsets of the finished occurrence are remembered, the old
    rows are dropped and fresh pending alerts are created for the new
    occurrence.
    """
    from sqlalchemy import select

    from app.database.models import Reminder

    current = now or utcnow_naive()
    notif_repo = ReminderNotificationRepository(session)

    result = await session.execute(
        select(Reminder)
        .where(
            Reminder.is_active.is_(True),
            Reminder.repeat_type != "NONE",
            Reminder.reminder_datetime <= current,
        )
        .order_by(Reminder.reminder_datetime)
        .limit(50)
    )
    reminders = list(result.scalars().all())

    for reminder in reminders:
        offsets = await alert_offsets_of(session, reminder.id)
        while reminder.reminder_datetime <= current:
            reminder.reminder_datetime = next_occurrence(
                reminder.reminder_datetime, reminder.repeat_type
            )
        await notif_repo.delete_for_reminder(reminder.id)
        await session.flush()
        await sync_notifications(session, reminder, offsets, now=current)

    return len(reminders)


async def process_due_notifications(
    send_message, timezone_name: str
) -> dict[str, int]:
    """Deliver every due alert once. Returns ``{sent, failed, advanced}``."""
    counters = {"sent": 0, "failed": 0, "advanced": 0}

    async with get_session() as session:
        due = await collect_due(session)

    for alert in due:
        status = STATUS_SENT
        error: str | None = None
        try:
            await send_message(
                chat_id=alert.telegram_id,
                text=build_alert_message(alert, timezone_name),
            )
            counters["sent"] += 1
        except Exception as exc:  # noqa: BLE001 - Telegram errors are expected here
            # only the exception class is stored: never echo user content
            status = STATUS_FAILED
            error = type(exc).__name__
            counters["failed"] += 1
            logger.warning(
                "Reminder %s could not be delivered to %s (%s)",
                alert.reminder_id,
                alert.telegram_id,
                error,
            )

        async with get_session() as session:
            await ReminderNotificationRepository(session).mark_sent(
                alert.notification_id, utcnow_naive()
            )
            await NotificationLogRepository(session).record(
                user_id=alert.user_id,
                notification_type=TYPE_REMINDER,
                related_id=alert.reminder_id,
                status=status,
                error_message=error,
            )

    async with get_session() as session:
        counters["advanced"] = await advance_repeating(session)

    return counters
