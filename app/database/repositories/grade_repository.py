"""Repository for ``grade_items``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Course, GradeItem
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

    async def count_for_user(self, user_id: int) -> int:
        """Total grade items across every course of one user."""
        stmt = (
            select(func.count(GradeItem.id))
            .join(Course, Course.id == GradeItem.course_id)
            .where(Course.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def summary_by_user(self, user_id: int) -> dict[int, tuple[int, float, float]]:
        """Per-course ``(item_count, total, maximum)`` for all of a user's courses."""
        stmt = (
            select(
                GradeItem.course_id,
                func.count(GradeItem.id),
                func.coalesce(func.sum(GradeItem.score), 0.0),
                func.coalesce(func.sum(GradeItem.max_score), 0.0),
            )
            .join(Course, Course.id == GradeItem.course_id)
            .where(Course.user_id == user_id)
            .group_by(GradeItem.course_id)
        )
        result = await self._session.execute(stmt)
        return {
            int(row[0]): (int(row[1]), float(row[2]), float(row[3]))
            for row in result.all()
        }
