"""Repository for ``notification_logs``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import NotificationLog


class NotificationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        user_id: int | None,
        notification_type: str,
        related_id: int | None,
        status: str,
        error_message: str | None = None,
    ) -> NotificationLog:
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            related_id=related_id,
            status=status,
            error_message=error_message,
        )
        self._session.add(log)
        await self._session.flush()
        return log

    async def count_by_status(self, notification_type: str | None = None) -> dict[str, int]:
        stmt = select(NotificationLog.status, func.count()).group_by(NotificationLog.status)
        if notification_type:
            stmt = stmt.where(NotificationLog.notification_type == notification_type)
        result = await self._session.execute(stmt)
        return {str(status): int(count) for status, count in result.all()}

    async def recent(self, limit: int = 20) -> list[NotificationLog]:
        stmt = (
            select(NotificationLog)
            .order_by(NotificationLog.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
