"""Repository for the ``admins`` table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Admin


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Admin | None:
        stmt = select(Admin).where(Admin.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_admin(self, telegram_id: int, *, allow_config: bool = True) -> bool:
        """An account is an admin when it exists in the ``admins`` table.

        ``allow_config`` additionally accepts ids listed in ``ADMIN_IDS``
        (so the first admin can bootstrap himself with ``/admin``).
        """
        from app.config import get_settings

        admin = await self.get_by_telegram_id(telegram_id)
        if admin is not None and admin.is_active:
            return True
        if allow_config:
            return get_settings().is_admin(telegram_id)
        return False

    async def upsert(
        self, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> Admin:
        admin = await self.get_by_telegram_id(telegram_id)
        if admin is None:
            admin = Admin(telegram_id=telegram_id, username=username, first_name=first_name)
            self._session.add(admin)
        else:
            admin.username = username
            admin.first_name = first_name
            admin.is_active = True
        await self._session.flush()
        return admin

    async def list_all(self) -> list[Admin]:
        result = await self._session.execute(select(Admin).order_by(Admin.id))
        return list(result.scalars().all())
