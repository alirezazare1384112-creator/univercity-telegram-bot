"""Repositories for ``reminders`` and ``reminder_notifications``."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Reminder, ReminderNotification, User
from app.database.models.reminder import (
    ALERT_TDELTA_HOURS,
    REPEAT_DAILY,
    REPEAT_MONTHLY,
    REPEAT_WEEKLY,
)


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int, *, active_only: bool = True) -> list[Reminder]:
        stmt = select(Reminder).where(Reminder.user_id == user_id)
        if active_only:
            stmt = stmt.where(Reminder.is_active.is_(True))
        stmt = stmt.order_by(Reminder.reminder_datetime)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, reminder_id: int, user_id: int) -> Reminder | None:
        stmt = select(Reminder).where(
            Reminder.id == reminder_id, Reminder.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, **fields: object) -> Reminder:
        reminder = Reminder(**fields)  # type: ignore[arg-type]
        self._session.add(reminder)
        await self._session.flush()
        return reminder

    async def update(self, reminder: Reminder, **fields: object) -> Reminder:
        for key, value in fields.items():
            if not hasattr(reminder, key):
                raise AttributeError(f"Reminder has no field {key!r}")
            setattr(reminder, key, value)
        await self._session.flush()
        return reminder

    async def delete(self, reminder: Reminder) -> None:
        await self._session.delete(reminder)
        await self._session.flush()

    async def count(self, user_id: int, *, active_only: bool = False) -> int:
        stmt = select(func.count()).select_from(Reminder).where(Reminder.user_id == user_id)
        if active_only:
            stmt = stmt.where(Reminder.is_active.is_(True))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def next_active(self, user_id: int, not_before: datetime) -> Reminder | None:
        """Soonest active reminder at/after ``not_before`` — one indexed row."""
        stmt = (
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.is_active.is_(True),
                Reminder.reminder_datetime >= not_before,
            )
            .order_by(Reminder.reminder_datetime)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class ReminderNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_reminder(self, reminder_id: int) -> list[ReminderNotification]:
        stmt = (
            select(ReminderNotification)
            .where(ReminderNotification.reminder_id == reminder_id)
            .order_by(ReminderNotification.fire_datetime)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def pending_for_reminder(self, reminder_id: int) -> list[ReminderNotification]:
        stmt = (
            select(ReminderNotification)
            .where(
                ReminderNotification.reminder_id == reminder_id,
                ReminderNotification.is_sent.is_(False),
            )
            .order_by(ReminderNotification.fire_datetime)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_reminder(self, reminder_id: int) -> None:
        await self._session.execute(
            delete(ReminderNotification).where(
                ReminderNotification.reminder_id == reminder_id
            )
        )

    async def create(
        self, *, reminder_id: int, alert_offset: str, fire_datetime: datetime
    ) -> ReminderNotification:
        notification = ReminderNotification(
            reminder_id=reminder_id,
            alert_offset=alert_offset,
            fire_datetime=fire_datetime,
            is_sent=False,
        )
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def mark_sent(self, notification_id: int, when: datetime) -> None:
        await self._session.execute(
            update(ReminderNotification)
            .where(ReminderNotification.id == notification_id)
            .values(is_sent=True, sent_at=when)
        )

    async def due(self, now: datetime, limit: int = 50) -> list[tuple]:
        """Pending alerts whose moment has arrived.

        Returns ``(notification, reminder, user)`` triples; the caller must
        only read scalar attributes (the session may already be closed).
        """
        stmt = (
            select(ReminderNotification, Reminder, User)
            .join(Reminder, Reminder.id == ReminderNotification.reminder_id)
            .join(User, User.id == Reminder.user_id)
            .where(
                ReminderNotification.is_sent.is_(False),
                ReminderNotification.fire_datetime <= now,
                Reminder.is_active.is_(True),
                User.is_active.is_(True),
            )
            .order_by(ReminderNotification.fire_datetime)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.all())


def next_occurrence(moment: datetime, repeat_type: str) -> datetime:
    """Advance a reminder by one period (calendar safe for MONTHLY)."""
    if repeat_type == REPEAT_DAILY:
        return moment + timedelta(days=1)
    if repeat_type == REPEAT_WEEKLY:
        return moment + timedelta(days=7)
    if repeat_type == REPEAT_MONTHLY:
        year, month = moment.year, moment.month + 1
        if month > 12:
            year, month = year + 1, 1
        try:
            return moment.replace(year=year, month=month)
        except ValueError:
            # e.g. 31 January -> 28/29 February
            return moment.replace(year=year, month=month, day=28)
    return moment


def fire_datetimes(
    reminder_datetime: datetime, alert_offsets: list[str] | tuple[str, ...]
) -> list[tuple[str, datetime]]:
    """``[(offset, fire_datetime), ...]`` for one occurrence."""
    pairs: list[tuple[str, datetime]] = []
    for offset in alert_offsets:
        hours = ALERT_TDELTA_HOURS.get(offset)
        if hours is None:
            continue
        pairs.append((offset, reminder_datetime - timedelta(hours=hours)))
    return pairs
