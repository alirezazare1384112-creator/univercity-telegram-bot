"""Pydantic schemas for the Mini App API responses."""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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


class GradeItemIn(BaseModel):
    title: str
    score: float
    max_score: float = 100.0
    kind: str = "OTHER"
    description: str | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title is required")
        if len(value) > 64:
            raise ValueError("title is too long")
        return value

    @field_validator("score")
    @classmethod
    def _score_positive(cls, value: float) -> float:
        if value < 0:
            raise ValueError("score must not be negative")
        return value

    @field_validator("max_score")
    @classmethod
    def _max_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("max_score must be positive")
        return value

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        from app.database.models.grade import GRADE_KINDS

        if value not in GRADE_KINDS:
            raise ValueError("unknown kind")
        return value

    @field_validator("description")
    @classmethod
    def _empty_desc_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _score_within_max(self) -> GradeItemIn:
        if self.score > self.max_score:
            raise ValueError("score must not exceed max_score")
        return self


class GradeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    score: float
    max_score: float
    kind: str
    description: str | None
    percent: float


class GradeTotals(BaseModel):
    total: float
    maximum: float
    percent: float


class CourseGradesOut(BaseModel):
    course: CourseOut
    items: list[GradeItemOut]
    totals: GradeTotals


class NoteIn(BaseModel):
    title: str
    description: str | None = None
    course_id: int | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title is required")
        if len(value) > 128:
            raise ValueError("title is too long")
        return value

    @field_validator("description")
    @classmethod
    def _empty_desc_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class NoteOut(BaseModel):
    id: int
    title: str
    description: str | None
    course_id: int | None
    course_name: str | None
    file_type: str
    file_name: str | None


class CalendarEventIn(BaseModel):
    title: str
    event_date: date
    event_time: time | None = None
    description: str | None = None
    is_done: bool = False

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title is required")
        if len(value) > 128:
            raise ValueError("title is too long")
        return value

    @field_validator("event_date")
    @classmethod
    def _sane_date(cls, value: date) -> date:
        if not date(2000, 1, 1) <= value <= date(2100, 12, 31):
            raise ValueError("event_date is out of range")
        return value

    @field_validator("description")
    @classmethod
    def _empty_desc_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CalendarEventOut(BaseModel):
    id: int
    title: str
    event_date: date
    event_time: str | None
    date_label: str
    description: str | None
    is_done: bool
