"""One-shot aggregates for the Mini App dashboard.

The home screen needs a handful of small per-user counters; issuing them as
scalar subqueries in a single SELECT keeps the dashboard at one round trip
instead of one query per card.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Announcement,
    CalendarEvent,
    Course,
    GradeItem,
    Note,
    Reminder,
    UniversityLink,
    WeeklySchedule,
)


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def counts(
        self, user_id: int, today: date
    ) -> tuple[int, int, int, int, int, int, int, int]:
        """Return every dashboard counter for one user in a single query.

        ``(courses, notes, announcements, links, active_reminders,
        grade_items, has_schedule, events_today)`` — the last two are
        booleans-in-disguise (0/1) derived from indexed columns.
        """

        def count(model: type, *criteria: object):
            return select(func.count()).select_from(model).where(*criteria).scalar_subquery()

        grade_items = (
            select(func.count(GradeItem.id))
            .join(Course, Course.id == GradeItem.course_id)
            .where(Course.user_id == user_id)
            .scalar_subquery()
        )
        stmt = select(
            count(Course, Course.user_id == user_id),
            count(Note, Note.user_id == user_id),
            count(Announcement, Announcement.user_id == user_id),
            count(UniversityLink, UniversityLink.user_id == user_id),
            count(Reminder, Reminder.user_id == user_id, Reminder.is_active.is_(True)),
            grade_items,
            count(
                WeeklySchedule,
                WeeklySchedule.user_id == user_id,
                WeeklySchedule.is_active.is_(True),
            ),
            count(
                CalendarEvent,
                CalendarEvent.user_id == user_id,
                CalendarEvent.is_done.is_(False),
                CalendarEvent.event_date == today,
            ),
        )
        row = (await self._session.execute(stmt)).one()
        return tuple(int(value) for value in row)  # type: ignore[return-value]
