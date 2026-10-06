from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import current_user
from app.api.schemas import CalendarEventIn, CalendarEventOut
from app.database.database import get_session
from app.database.models import CalendarEvent, User
from app.database.repositories.calendar_event_repository import CalendarEventRepository
from app.utils.datetime_utils import format_jalali_date

router = APIRouter(prefix="/api", tags=["calendar"])


def _event_out(event: CalendarEvent) -> CalendarEventOut:
    return CalendarEventOut(
        id=event.id,
        title=event.title,
        event_date=event.event_date,
        event_time=event.event_time.strftime("%H:%M") if event.event_time else None,
        date_label=format_jalali_date(event.event_date),
        description=event.description,
        is_done=event.is_done,
    )


@router.get("/calendar", response_model=list[CalendarEventOut])
async def list_events(
    user: Annotated[User, Depends(current_user)],
    done: bool = Query(default=False),
) -> list[CalendarEventOut]:
    async with get_session() as session:
        events = await CalendarEventRepository(session).list_by_user(user.id, done=done)
    return [_event_out(event) for event in events]


@router.post("/calendar", response_model=CalendarEventOut)
async def create_event(
    payload: CalendarEventIn,
    user: Annotated[User, Depends(current_user)],
) -> CalendarEventOut:
    async with get_session() as session:
        event = await CalendarEventRepository(session).create(
            user_id=user.id,
            title=payload.title,
            event_date=payload.event_date,
            event_time=payload.event_time,
            description=payload.description,
        )
    return _event_out(event)


@router.put("/calendar/{event_id}", response_model=CalendarEventOut)
async def update_event(
    event_id: int,
    payload: CalendarEventIn,
    user: Annotated[User, Depends(current_user)],
) -> CalendarEventOut:
    async with get_session() as session:
        repository = CalendarEventRepository(session)
        event = await repository.get(event_id, user.id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        event = await repository.update(
            event,
            title=payload.title,
            event_date=payload.event_date,
            event_time=payload.event_time,
            description=payload.description,
            is_done=payload.is_done,
        )
    return _event_out(event)


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
