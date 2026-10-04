"""Repository for the ``users`` table.

Handlers and services never write SQL - they call a repository.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_from_telegram(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> tuple[User, bool]:
        """Upsert in a single SELECT; returns ``(user, created)``."""
        user = await self.get_by_telegram_id(telegram_id)
        created = user is None
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )
            self._session.add(user)
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
        await self._session.flush()
        return user, created

    async def upsert_from_telegram(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        """Create the user on first contact, refresh profile data later."""
        user, _ = await self.get_or_create_from_telegram(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def update_profile(self, user: User, **fields: object) -> User:
        for key, value in fields.items():
            if not hasattr(user, key):
                raise AttributeError(f"User has no field {key!r}")
            setattr(user, key, value)
        await self._session.flush()
        return user

    async def list_users(self, *, active_only: bool = False, limit: int = 100) -> list[User]:
        stmt = select(User).order_by(User.id.desc()).limit(limit)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_telegram_ids(self) -> list[int]:
        stmt = select(User.telegram_id).where(User.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_ids(self) -> list[int]:
        """Internal ids of every active user (broadcast / import)."""
        stmt = select(User.id).where(User.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, active_only: bool = False) -> int:
        stmt = select(func.count()).select_from(User)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def deactivate(self, user: User) -> User:
        user.is_active = False
        await self._session.flush()
        return user
