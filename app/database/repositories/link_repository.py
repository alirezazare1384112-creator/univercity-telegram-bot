"""Repository for ``university_links``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UniversityLink


class LinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> list[UniversityLink]:
        stmt = (
            select(UniversityLink)
            .where(UniversityLink.user_id == user_id)
            .order_by(UniversityLink.title)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, link_id: int, user_id: int) -> UniversityLink | None:
        stmt = select(UniversityLink).where(
            UniversityLink.id == link_id, UniversityLink.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        url: str,
        description: str | None = None,
        ciphertext_b64: str | None = None,
        wrapped_key_b64: str | None = None,
    ) -> UniversityLink:
        link = UniversityLink(
            user_id=user_id,
            title=title,
            url=url,
            description=description or None,
            ciphertext_b64=ciphertext_b64,
            wrapped_key_b64=wrapped_key_b64,
        )
        self._session.add(link)
        await self._session.flush()
        return link

    async def update(self, link: UniversityLink, **fields: object) -> UniversityLink:
        for key, value in fields.items():
            if not hasattr(link, key):
                raise AttributeError(f"UniversityLink has no field {key!r}")
            setattr(link, key, value)
        await self._session.flush()
        return link

    async def delete(self, link: UniversityLink) -> None:
        await self._session.delete(link)
        await self._session.flush()

    async def count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(UniversityLink).where(
            UniversityLink.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
