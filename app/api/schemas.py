"""Pydantic schemas for the Mini App API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    student_number: str | None
    field_of_study: str | None
    university: str | None
    semester: str | None
    bio: str | None


class DashboardCounts(BaseModel):
    courses: int
    notes: int
    announcements: int
    reminders: int
    events_today: int
    links: int


class NextReminder(BaseModel):
    id: int
    title: str
    when: str


class DashboardOut(BaseModel):
    user: MeOut
    today: str
    counts: DashboardCounts
    schedule: bool
    next_reminder: NextReminder | None
