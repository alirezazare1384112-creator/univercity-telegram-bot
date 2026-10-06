"""Repository for ``grade_items``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import GradeItem
from app.database.models.grade import GRADE_KIND_OTHER


class GradeItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_course(self, course_id: int) -> list[GradeItem]:
        stmt = (
            select(GradeItem)
            .where(GradeItem.course_id == course_id)
            .order_by(GradeItem.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, item_id: int, course_id: int) -> GradeItem | None:
        stmt = select(GradeItem).where(
            GradeItem.id == item_id, GradeItem.course_id == course_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        course_id: int,
        title: str,
        score: float,
        max_score: float,
        description: str | None = None,
        kind: str = GRADE_KIND_OTHER,
    ) -> GradeItem:
        item = GradeItem(
            course_id=course_id,
            title=title,
            score=score,
            max_score=max_score,
            description=description or None,
            kind=kind,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def update(self, item: GradeItem, **fields: object) -> GradeItem:
        for key, value in fields.items():
            if not hasattr(item, key):
                raise AttributeError(f"GradeItem has no field {key!r}")
            setattr(item, key, value)
        await self._session.flush()
        return item

    async def delete(self, item: GradeItem) -> None:
        await self._session.delete(item)
        await self._session.flush()

    async def totals(self, course_id: int) -> tuple[float, float]:
        """Sum of scores and of maximum scores for one course."""
        stmt = select(
            func.coalesce(func.sum(GradeItem.score), 0.0),
            func.coalesce(func.sum(GradeItem.max_score), 0.0),
        ).where(GradeItem.course_id == course_id)
        result = await self._session.execute(stmt)
        row = result.one()
        return float(row[0]), float(row[1])

    async def count(self, course_id: int) -> int:
        stmt = select(func.count()).select_from(GradeItem).where(
            GradeItem.course_id == course_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
