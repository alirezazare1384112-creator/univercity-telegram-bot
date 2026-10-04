"""Repository for ``weekly_schedules``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WeeklySchedule


class WeeklyScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, user_id: int) -> WeeklySchedule | None:
        stmt = select(WeeklySchedule).where(
            WeeklySchedule.user_id == user_id,
            WeeklySchedule.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save(
        self,
        *,
        user_id: int,
        telegram_file_id: str,
        file_unique_id: str | None,
        file_type: str = "photo",
        caption: str | None = None,
    ) -> WeeklySchedule:
        """Insert or replace the active schedule of a student."""
        schedule = await self.get_active(user_id)
        if schedule is None:
            schedule = WeeklySchedule(user_id=user_id, is_active=True)
            self._session.add(schedule)

        schedule.telegram_file_id = telegram_file_id
        schedule.file_unique_id = file_unique_id
        schedule.file_type = file_type
        schedule.caption = caption
        schedule.is_active = True
        await self._session.flush()
        return schedule

    async def delete_active(self, user_id: int) -> bool:
        """Remove the active schedule. Returns ``False`` if there was none."""
        schedule = await self.get_active(user_id)
        if schedule is None:
            return False
        await self._session.delete(schedule)
        await self._session.flush()
        return True

    async def count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(WeeklySchedule).where(
            WeeklySchedule.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
