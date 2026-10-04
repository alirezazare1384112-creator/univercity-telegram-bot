"""Repository for ``announcements``.

Every read/write is scoped by ``user_id`` so one student's inbox stays
private to that student.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Announcement
from app.database.models.announcement import ANNOUNCEMENT_TELEGRAM, MAX_TEXT_LENGTH


class AnnouncementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> list[Announcement]:
        stmt = (
            select(Announcement)
            .where(Announcement.user_id == user_id)
            # newest first: students look for today's announcement
            .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, announcement_id: int, user_id: int) -> Announcement | None:
        stmt = select(Announcement).where(
            Announcement.id == announcement_id, Announcement.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        source: str = ANNOUNCEMENT_TELEGRAM,
        text: str | None = None,
        source_url: str | None = None,
        file_type: str | None = None,
        file_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Announcement:
        announcement = Announcement(
            user_id=user_id,
            source=source,
            title=title[:128],
            text=(text or "").strip()[:MAX_TEXT_LENGTH] or None,
            source_url=source_url,
            file_type=file_type,
            file_id=file_id,
        )
        if created_at is not None:
            announcement.created_at = created_at
        self._session.add(announcement)
        await self._session.flush()
        return announcement

    async def delete(self, announcement: Announcement) -> None:
        await self._session.delete(announcement)
        await self._session.flush()

    async def existing_source_urls(self, user_id: int, urls: list[str]) -> set[str]:
        """Which of ``urls`` the user already has (import dedup)."""
        if not urls:
            return set()
        stmt = select(Announcement.source_url).where(
            Announcement.user_id == user_id,
            Announcement.source_url.in_(urls),
        )
        result = await self._session.execute(stmt)
        return {url for url in result.scalars().all() if url}

    async def count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Announcement).where(
            Announcement.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
