"""Repository for ``user_channels`` - per-user channel subscriptions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user_channel import UserChannel


class UserChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> list[UserChannel]:
        stmt = (
            select(UserChannel)
            .where(UserChannel.user_id == user_id)
            .order_by(UserChannel.created_at.desc(), UserChannel.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[UserChannel]:
        """Every subscription of every user (the sync loop consumes this)."""
        stmt = select(UserChannel).order_by(UserChannel.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, channel_id: int, user_id: int) -> UserChannel | None:
        stmt = select(UserChannel).where(
            UserChannel.id == channel_id, UserChannel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(
        self, *, user_id: int, platform: str, url: str, handle: str
    ) -> tuple[UserChannel, bool]:
        """Insert the subscription; ``(channel, created=False)`` when it exists."""
        existing = await self._find(user_id, url)
        if existing is not None:
            return existing, False
        channel = UserChannel(user_id=user_id, platform=platform, url=url, handle=handle)
        self._session.add(channel)
        await self._session.flush()
        return channel, True

    async def delete(self, channel: UserChannel) -> None:
        await self._session.delete(channel)
        await self._session.flush()

    async def _find(self, user_id: int, url: str) -> UserChannel | None:
        stmt = select(UserChannel).where(
            UserChannel.user_id == user_id, UserChannel.url == url
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
