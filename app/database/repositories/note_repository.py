"""Repository for ``notes``.

Every read/write is scoped by ``user_id`` so one student can never touch
another student's files.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Note


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(
        self, user_id: int, *, course_id: int | None = None
    ) -> list[Note]:
        stmt = select(Note).where(Note.user_id == user_id)
        if course_id is not None:
            stmt = stmt.where(Note.course_id == course_id)
        # newest first: students add files right before they need them
        stmt = stmt.order_by(Note.created_at.desc(), Note.id.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, note_id: int, user_id: int) -> Note | None:
        stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        file_type: str,
        file_id: str,
        course_id: int | None = None,
        description: str | None = None,
        file_unique_id: str | None = None,
        file_name: str | None = None,
    ) -> Note:
        note = Note(
            user_id=user_id,
            course_id=course_id,
            title=title,
            description=description or None,
            file_type=file_type,
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file_name,
        )
        self._session.add(note)
        await self._session.flush()
        return note

    async def update(self, note: Note, **fields: object) -> Note:
        for key, value in fields.items():
            if not hasattr(note, key):
                raise AttributeError(f"Note has no field {key!r}")
            setattr(note, key, value)
        await self._session.flush()
        return note

    async def delete(self, note: Note) -> None:
        await self._session.delete(note)
        await self._session.flush()

    async def count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Note).where(Note.user_id == user_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
