"""Repository for ``weekly_activities``.

All reads/writes are scoped by ``user_id``. Activities are listed
grouped by weekday so the planner UI can render seven columns without
re-sorting on the client.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WeeklyActivity


class WeeklyActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> list[WeeklyActivity]:
        """All activities for a user, ordered by day then start time."""
        stmt = (
            select(WeeklyActivity)
            .where(WeeklyActivity.user_id == user_id)
            .order_by(
                WeeklyActivity.day_of_week.asc(),
                WeeklyActivity.start_time.asc(),
                WeeklyActivity.id.asc(),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_day(
        self, user_id: int, day_of_week: int
    ) -> list[WeeklyActivity]:
        """Activities for one weekday, ordered by start time."""
        stmt = (
            select(WeeklyActivity)
            .where(
                WeeklyActivity.user_id == user_id,
                WeeklyActivity.day_of_week == day_of_week,
            )
            .order_by(WeeklyActivity.start_time.asc(), WeeklyActivity.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, activity_id: int, user_id: int) -> WeeklyActivity | None:
        stmt = select(WeeklyActivity).where(
            WeeklyActivity.id == activity_id,
            WeeklyActivity.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        day_of_week: int,
        start_time,
        duration_hours: float,
        description: str | None = None,
        category: str = "OTHER",
        is_active: bool = True,
    ) -> WeeklyActivity:
        activity = WeeklyActivity(
            user_id=user_id,
            title=title,
            day_of_week=day_of_week,
            start_time=start_time,
            duration_hours=duration_hours,
            description=description or None,
            category=category,
            is_active=is_active,
        )
        self._session.add(activity)
        await self._session.flush()
        return activity

    async def update(
        self, activity: WeeklyActivity, **fields: object
    ) -> WeeklyActivity:
        for key, value in fields.items():
            if not hasattr(activity, key):
                raise AttributeError(f"WeeklyActivity has no field {key!r}")
            setattr(activity, key, value)
        await self._session.flush()
        return activity

    async def delete(self, activity: WeeklyActivity) -> None:
        await self._session.delete(activity)
        await self._session.flush()

    async def count(self, user_id: int) -> int:
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(WeeklyActivity)
            .where(WeeklyActivity.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
