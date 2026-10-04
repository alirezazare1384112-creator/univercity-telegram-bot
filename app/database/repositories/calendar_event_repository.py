"""Repository for ``calendar_events``.

Reads/writes are scoped by ``user_id``; the two list views are
"still pending" (menu) and "already done".
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CalendarEvent


class CalendarEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int, *, done: bool = False) -> list[CalendarEvent]:
        stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == user_id, CalendarEvent.is_done.is_(done)
        )
        if done:
            # newest completed first: useful when looking something up again
            stmt = stmt.order_by(CalendarEvent.event_date.desc(), CalendarEvent.id.desc())
        else:
            # overdue items come first, then the soonest ones
            stmt = stmt.order_by(
                CalendarEvent.event_date.asc(),
                CalendarEvent.event_time.asc(),
                CalendarEvent.id.asc(),
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, event_id: int, user_id: int) -> CalendarEvent | None:
        stmt = select(CalendarEvent).where(
            CalendarEvent.id == event_id, CalendarEvent.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        event_date,
        event_time=None,
        description: str | None = None,
    ) -> CalendarEvent:
        event = CalendarEvent(
            user_id=user_id,
            title=title,
            event_date=event_date,
            event_time=event_time,
            description=description or None,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def update(self, event: CalendarEvent, **fields: object) -> CalendarEvent:
        for key, value in fields.items():
            if not hasattr(event, key):
                raise AttributeError(f"CalendarEvent has no field {key!r}")
            setattr(event, key, value)
        await self._session.flush()
        return event

    async def delete(self, event: CalendarEvent) -> None:
        await self._session.delete(event)
        await self._session.flush()

    async def count(self, user_id: int, *, done: bool = False) -> int:
        stmt = (
            select(func.count())
            .select_from(CalendarEvent)
            .where(CalendarEvent.user_id == user_id, CalendarEvent.is_done.is_(done))
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
