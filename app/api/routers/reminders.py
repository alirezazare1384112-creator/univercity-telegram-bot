from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import current_user
from app.api.routers.courses import _own_course
from app.api.schemas import ReminderIn, ReminderOut
from app.config import get_settings
from app.database.database import get_session
from app.database.models import Reminder, User
from app.database.models.reminder import REPEAT_LABELS
from app.database.repositories.course_repository import CourseRepository
from app.database.repositories.reminder_repository import (
    ReminderNotificationRepository,
    ReminderRepository,
)
from app.services.reminder_service import alert_offsets_of, sync_notifications
from app.utils.datetime_utils import format_jalali, local_to_utc_naive, utc_to_local

router = APIRouter(prefix="/api", tags=["reminders"])


async def _out(session, reminder: Reminder, course_names: dict[int, str]) -> ReminderOut:
    tz = get_settings().timezone
    offsets = await alert_offsets_of(session, reminder.id)
    local = utc_to_local(reminder.reminder_datetime, tz).replace(tzinfo=None)
    return ReminderOut(
        id=reminder.id,
        title=reminder.title,
        description=reminder.description,
        course_id=reminder.course_id,
        course_name=course_names.get(reminder.course_id) if reminder.course_id else None,
        local_datetime=local,
        display=format_jalali(reminder.reminder_datetime, tz),
        repeat_type=reminder.repeat_type,
        repeat_label=REPEAT_LABELS.get(reminder.repeat_type, reminder.repeat_type),
        is_active=reminder.is_active,
        alert_offsets=offsets,
    )


async def _names_for(session, user: User) -> dict[int, str]:
    courses = await CourseRepository(session).list_by_user(user.id)
    return {course.id: course.name for course in courses}


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(
    user: Annotated[User, Depends(current_user)],
    active_only: bool = Query(default=False),
) -> list[ReminderOut]:
    async with get_session() as session:
        reminders = await ReminderRepository(session).list_by_user(
            user.id, active_only=active_only
        )
        names = await _names_for(session, user)
        return [await _out(session, reminder, names) for reminder in reminders]


@router.post("/reminders", response_model=ReminderOut)
async def create_reminder(
    payload: ReminderIn,
    user: Annotated[User, Depends(current_user)],
) -> ReminderOut:
    tz = get_settings().timezone
    async with get_session() as session:
        names: dict[int, str] = {}
        if payload.course_id is not None:
            course = await _own_course(session, payload.course_id, user)
            names[course.id] = course.name
        reminder = await ReminderRepository(session).create(
            user_id=user.id,
            course_id=payload.course_id,
            title=payload.title,
            description=payload.description,
            reminder_datetime=local_to_utc_naive(payload.local_datetime, tz),
            repeat_type=payload.repeat_type,
            is_active=payload.is_active,
        )
        await sync_notifications(session, reminder, payload.alert_offsets)
        return await _out(session, reminder, names)


@router.put("/reminders/{reminder_id}", response_model=ReminderOut)
async def update_reminder(
    reminder_id: int,
    payload: ReminderIn,
    user: Annotated[User, Depends(current_user)],
) -> ReminderOut:
    tz = get_settings().timezone
    async with get_session() as session:
        repository = ReminderRepository(session)
        reminder = await repository.get(reminder_id, user.id)
        if reminder is None:
            raise HTTPException(status_code=404, detail="reminder not found")
        names: dict[int, str] = {}
        if payload.course_id is not None:
            course = await _own_course(session, payload.course_id, user)
            names[course.id] = course.name
        reminder = await repository.update(
            reminder,
            title=payload.title,
            description=payload.description,
            course_id=payload.course_id,
            reminder_datetime=local_to_utc_naive(payload.local_datetime, tz),
            repeat_type=payload.repeat_type,
            is_active=payload.is_active,
        )
        await sync_notifications(session, reminder, payload.alert_offsets)
        return await _out(session, reminder, names)


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(
    reminder_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = ReminderRepository(session)
        reminder = await repository.get(reminder_id, user.id)
        if reminder is None:
            raise HTTPException(status_code=404, detail="reminder not found")
        await ReminderNotificationRepository(session).delete_for_reminder(reminder.id)
        await repository.delete(reminder)
    return {"deleted": True}
