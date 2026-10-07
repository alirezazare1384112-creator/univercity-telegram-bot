"""/api/dashboard - aggregated data for the Mini App home screen."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.schemas import DashboardCounts, DashboardOut, MeOut, NextReminder
from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.dashboard_repository import DashboardRepository
from app.database.repositories.reminder_repository import ReminderRepository
from app.utils.datetime_utils import format_jalali, format_jalali_date, utc_to_local, utcnow_naive

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def read_dashboard(user: Annotated[User, Depends(current_user)]) -> DashboardOut:
    settings = get_settings()
    now_utc = utcnow_naive()
    today_local = utc_to_local(now_utc, settings.timezone).date()

    async with get_session() as session:
        (
            courses,
            notes,
            announcements,
            links,
            active_reminders,
            grade_items,
            schedule_rows,
            events_today,
        ) = await DashboardRepository(session).counts(user.id, today_local)
        upcoming = await ReminderRepository(session).next_active(user.id, now_utc)

    next_reminder = (
        NextReminder(
            id=upcoming.id,
            title=upcoming.title,
            when=format_jalali(upcoming.reminder_datetime, settings.timezone),
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
            reminders=active_reminders,
            events_today=events_today,
            links=links,
            grade_items=grade_items,
        ),
        schedule=schedule_rows > 0,
        next_reminder=next_reminder,
    )
