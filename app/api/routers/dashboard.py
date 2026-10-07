"""/api/dashboard - aggregated data for the Mini App home screen."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import DashboardCounts, DashboardOut, MeOut, NextReminder
from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.announcement_repository import AnnouncementRepository
from app.database.repositories.calendar_event_repository import CalendarEventRepository
from app.database.repositories.course_repository import CourseRepository
from app.database.repositories.grade_repository import GradeItemRepository
from app.database.repositories.link_repository import LinkRepository
from app.database.repositories.note_repository import NoteRepository
from app.database.repositories.reminder_repository import ReminderRepository
from app.database.repositories.schedule_repository import WeeklyScheduleRepository
from app.utils.datetime_utils import format_jalali, format_jalali_date, utc_to_local, utcnow_naive

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def read_dashboard(user: Annotated[User, Depends(current_user)]) -> DashboardOut:
    settings = get_settings()
    now_utc = utcnow_naive()
    today_local = utc_to_local(now_utc, settings.timezone).date()

    async with get_session() as session:
        courses = await CourseRepository(session).count(user.id)
        notes = await NoteRepository(session).count(user.id)
        announcements = await AnnouncementRepository(session).count(user.id)
        links = await LinkRepository(session).count(user.id)
        grade_items = await GradeItemRepository(session).count_for_user(user.id)
        reminders = await ReminderRepository(session).count(user.id, active_only=True)
        events = await CalendarEventRepository(session).list_by_user(user.id)
        schedule = await WeeklyScheduleRepository(session).get_active(user.id)
        active_reminders = await ReminderRepository(session).list_by_user(user.id, active_only=True)

    events_today = sum(1 for event in events if event.event_date == today_local)
    upcoming = sorted(
        (r for r in active_reminders if r.reminder_datetime >= now_utc),
        key=lambda r: r.reminder_datetime,
    )
    next_reminder = (
        NextReminder(
            id=upcoming[0].id,
            title=upcoming[0].title,
            when=format_jalali(upcoming[0].reminder_datetime, settings.timezone),
        )
        if upcoming
        else None
    )

    return DashboardOut(
        user=MeOut.model_validate(user),
        today=format_jalali_date(today_local),
        counts=DashboardCounts(
            courses=courses,
            notes=notes,
            announcements=announcements,
            reminders=reminders,
            events_today=events_today,
            links=links,
            grade_items=grade_items,
        ),
        schedule=schedule is not None,
        next_reminder=next_reminder,
    )
