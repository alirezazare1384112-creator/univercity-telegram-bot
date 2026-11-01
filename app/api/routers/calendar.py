from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import current_user
from app.api.schemas import CalendarEventIn, CalendarEventOut
from app.database.database import get_session
from app.database.models import CalendarEvent, User
from app.database.repositories.calendar_event_repository import CalendarEventRepository
from app.database.repositories.course_repository import CourseRepository
from app.utils.datetime_utils import format_jalali_date

router = APIRouter(prefix="/api", tags=["calendar"])


async def _course_name(session, course_id: int | None) -> str | None:
    if course_id is None:
        return None
    course = await CourseRepository(session).get(course_id, 0)  # type: ignore[arg-type]
    return course.name if course else None


def _event_out(event: CalendarEvent, course_name: str | None = None) -> CalendarEventOut:
    return CalendarEventOut(
        id=event.id,
        title=event.title,
        event_date=event.event_date,
        event_time=event.event_time.strftime("%H:%M") if event.event_time else None,
        date_label=format_jalali_date(event.event_date),
        description=event.description,
        is_done=event.is_done,
        event_type=event.event_type,
        course_id=event.course_id,
        course_name=course_name,
    )


@router.get("/calendar", response_model=list[CalendarEventOut])
async def list_events(
    user: Annotated[User, Depends(current_user)],
    done: bool = Query(default=False),
) -> list[CalendarEventOut]:
    async with get_session() as session:
        events = await CalendarEventRepository(session).list_by_user(user.id, done=done)
        courses = await CourseRepository(session).list_by_user(user.id)
    names = {c.id: c.name for c in courses}
    return [_event_out(e, names.get(e.course_id)) for e in events]


@router.post("/calendar", response_model=CalendarEventOut)
async def create_event(
    payload: CalendarEventIn,
    user: Annotated[User, Depends(current_user)],
) -> CalendarEventOut:
    course_name: str | None = None
    async with get_session() as session:
        if payload.course_id is not None:
            course = await CourseRepository(session).get(payload.course_id, user.id)
            if course is None:
                raise HTTPException(status_code=404, detail="course not found")
            course_name = course.name
        event = await CalendarEventRepository(session).create(
            user_id=user.id,
            title=payload.title,
            event_date=payload.event_date,
            event_time=payload.event_time,
            description=payload.description,
            event_type=payload.event_type,
            course_id=payload.course_id,
        )
    return _event_out(event, course_name)


@router.put("/calendar/{event_id}", response_model=CalendarEventOut)
async def update_event(
    event_id: int,
    payload: CalendarEventIn,
    user: Annotated[User, Depends(current_user)],
) -> CalendarEventOut:
    course_name: str | None = None
    async with get_session() as session:
        repository = CalendarEventRepository(session)
        event = await repository.get(event_id, user.id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        if payload.course_id is not None:
            course = await CourseRepository(session).get(payload.course_id, user.id)
            if course is None:
                raise HTTPException(status_code=404, detail="course not found")
            course_name = course.name
        event = await repository.update(
            event,
            title=payload.title,
            event_date=payload.event_date,
            event_time=payload.event_time,
            description=payload.description,
            is_done=payload.is_done,
            event_type=payload.event_type,
            course_id=payload.course_id,
        )
    return _event_out(event, course_name)


@router.delete("/calendar/{event_id}")
async def delete_event(
    event_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = CalendarEventRepository(session)
        event = await repository.get(event_id, user.id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        await repository.delete(event)
    return {"deleted": True}
