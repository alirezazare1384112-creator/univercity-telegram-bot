"""Global counters for the admin panel (whole tables, not per user)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Admin,
    Announcement,
    CalendarEvent,
    Course,
    GradeItem,
    Note,
    Reminder,
    UniversityLink,
    User,
    WeeklySchedule,
)


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def totals(self) -> dict[str, int]:
        return {
            "users": await self._count(User),
            "active_users": await self._count(User, User.is_active.is_(True)),
            "admins": await self._count(Admin),
            "courses": await self._count(Course),
            "grades": await self._count(GradeItem),
            "reminders": await self._count(Reminder),
            "announcements": await self._count(Announcement),
            "notes": await self._count(Note),
            "links": await self._count(UniversityLink),
            "events": await self._count(CalendarEvent),
            "schedules": await self._count(WeeklySchedule),
        }

    async def _count(self, model: type, *criteria: object) -> int:
        stmt = select(func.count()).select_from(model)
        if criteria:
            stmt = stmt.where(*criteria)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
