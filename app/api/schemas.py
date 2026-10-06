"""Pydantic schemas for the Mini App API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


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


class ScheduleOut(BaseModel):
    exists: bool
    file_type: str | None = None
    caption: str | None = None


class CourseIn(BaseModel):
    name: str
    units: int = 3
    teacher_name: str | None = None
    semester: str | None = None
    academic_year: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name is required")
        if len(value) > 128:
            raise ValueError("name is too long")
        return value

    @field_validator("units")
    @classmethod
    def _units_range(cls, value: int) -> int:
        if not 1 <= value <= 30:
            raise ValueError("units must be between 1 and 30")
        return value

    @field_validator("teacher_name", "semester", "academic_year")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    units: int
    teacher_name: str | None
    semester: str | None
    academic_year: str | None
