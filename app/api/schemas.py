"""Pydantic schemas for the Mini App API responses."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


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
    is_admin: bool = False


class AdminStatsOut(BaseModel):
    users: int
    active_users: int
    admins: int
    courses: int
    grades: int
    reminders: int
    announcements: int
    notes: int
    links: int
    events: int
    schedules: int


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    is_active: bool


class AdminUsersOut(BaseModel):
    total: int
    active: int
    users: list[AdminUserOut]


class DashboardCounts(BaseModel):
    courses: int
    notes: int
    announcements: int
    reminders: int
    events_today: int
    links: int
    grade_items: int


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


class CourseGradeSummary(BaseModel):
    """One row of the cross-course grades summary page."""

    course_id: int
    name: str
    item_count: int
    totals: GradeTotals


class GradesSummaryOut(BaseModel):
    courses: list[CourseGradeSummary]
    totals: GradeTotals
    item_count: int


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


class FileTokenOut(BaseModel):
    """Signed preview URL payload for ``<img>``/``<iframe>`` (header-less GET)."""

    token: str
    media_type: str


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


class ReminderIn(BaseModel):
    title: str
    local_datetime: datetime
    description: str | None = None
    course_id: int | None = None
    repeat_type: str = "NONE"
    is_active: bool = True
    alert_offsets: list[str] = Field(default_factory=lambda: ["AT_TIME"])

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

    @field_validator("repeat_type")
    @classmethod
    def _known_repeat(cls, value: str) -> str:
        from app.database.models.reminder import REPEAT_TYPES

        if value not in REPEAT_TYPES:
            raise ValueError("unknown repeat_type")
        return value

    @field_validator("alert_offsets")
    @classmethod
    def _known_offsets(cls, value: list[str]) -> list[str]:
        from app.database.models.reminder import ALERT_OFFSETS

        if not value:
            raise ValueError("at least one alert is required")
        unknown = [offset for offset in value if offset not in ALERT_OFFSETS]
        if unknown:
            raise ValueError("unknown alert offset")
        # keep order, drop duplicates
        seen: list[str] = []
        for offset in value:
            if offset not in seen:
                seen.append(offset)
        return seen


class ReminderOut(BaseModel):
    id: int
    title: str
    description: str | None
    course_id: int | None
    course_name: str | None
    local_datetime: datetime
    display: str
    repeat_type: str
    repeat_label: str
    is_active: bool
    alert_offsets: list[str]


class AnnouncementOut(BaseModel):
    id: int
    title: str
    text: str | None
    source: str
    source_url: str | None
    file_type: str | None
    created_at: datetime
    display: str


class ChannelIn(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("url is required")
        if len(value) > 255:
            raise ValueError("url is too long")
        return value


class ChannelOut(BaseModel):
    id: int
    platform: str
    url: str
    handle: str
    created_at: datetime


class LinkIn(BaseModel):
    title: str
    url: str
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

    @field_validator("url")
    @classmethod
    def _http_url_only(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        if len(value) > 255:
            raise ValueError("url is too long")
        return value

    @field_validator("description")
    @classmethod
    def _empty_desc_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str
    description: str | None


class ProfileIn(BaseModel):
    student_number: str | None = None
    field_of_study: str | None = None
    university: str | None = None
    semester: str | None = None
    bio: str | None = None

    @field_validator("student_number", "field_of_study", "university", "semester")
    @classmethod
    def _check_profile_field(cls, value: str | None, info: ValidationInfo) -> str | None:
        from app.utils.validation import validate_profile_field

        if value is None:
            return None
        if not value.strip():
            return None  # empty means "clear this field"
        ok, cleaned, error = validate_profile_field(str(info.field_name), value)
        if not ok:
            raise ValueError(error)
        return cleaned

    @field_validator("bio")
    @classmethod
    def _check_bio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 500:
            raise ValueError("bio is too long (max 500)")
        return value
