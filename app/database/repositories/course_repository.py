"""Repository for ``courses``.

Every read/write is scoped by ``user_id`` so one student can never touch
another student's data.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Course


class CourseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> list[Course]:
        stmt = (
            select(Course)
            .where(Course.user_id == user_id)
            .order_by(Course.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, course_id: int, user_id: int) -> Course | None:
        """Fetch a course only if it belongs to ``user_id``."""
        stmt = select(Course).where(
            Course.id == course_id, Course.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        name: str,
        units: int,
        teacher_name: str | None = None,
        semester: str | None = None,
        academic_year: str | None = None,
    ) -> Course:
        course = Course(
            user_id=user_id,
            name=name,
            units=units,
            teacher_name=teacher_name or None,
            semester=semester or None,
            academic_year=academic_year or None,
        )
        self._session.add(course)
        await self._session.flush()
        return course

    async def update(self, course: Course, **fields: object) -> Course:
        for key, value in fields.items():
            if not hasattr(course, key):
                raise AttributeError(f"Course has no field {key!r}")
            setattr(course, key, value)
        await self._session.flush()
        return course

    async def delete(self, course: Course) -> None:
        """Deleting a course also removes its grade items and notes
        (handled by the database through ON DELETE CASCADE)."""
        await self._session.delete(course)
        await self._session.flush()

    async def count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Course).where(Course.user_id == user_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
