"""CalendarEvent model - one future task / appointment of a student."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar

# Event types — used by the calendar for colour coding and filtering
EVENT_EXAM = "EXAM"
EVENT_QUIZ = "QUIZ"
EVENT_ASSIGNMENT = "ASSIGNMENT"
EVENT_PROJECT = "PROJECT"
EVENT_PRESENTATION = "PRESENTATION"
EVENT_CLASS = "CLASS"
EVENT_TASK = "TASK"
EVENT_OTHER = "OTHER"
EVENT_TYPES: tuple[str, ...] = (
    EVENT_EXAM,
    EVENT_QUIZ,
    EVENT_ASSIGNMENT,
    EVENT_PROJECT,
    EVENT_PRESENTATION,
    EVENT_CLASS,
    EVENT_TASK,
    EVENT_OTHER,
)

EVENT_LABELS: dict[str, str] = {
    EVENT_EXAM: "امتحان",
    EVENT_QUIZ: "کوییز",
    EVENT_ASSIGNMENT: "تکلیف",
    EVENT_PROJECT: "پروژه",
    EVENT_PRESENTATION: "ارائه",
    EVENT_CLASS: "کلاس",
    EVENT_TASK: "کار شخصی",
    EVENT_OTHER: "سایر",
}


class CalendarEvent(TimestampMixin, IdMixin, Base):
    """A dated item of the personal calendar (exam, deadline, meeting).

    Dates and times are stored exactly as the student meant them **in
    their local calendar** (``event_date``) and local clock
    (``event_time``): a calendar day is not a moment in UTC, so no
    timezone conversion ever touches these two columns. ``event_time`` is
    ``NULL`` for an all-day event.
    """

    __tablename__ = "calendar_events"
    __table_args__ = (
        Index("ix_calendar_events_user_id", "user_id"),
        CheckConstraint(
            "event_type IN ('EXAM','QUIZ','ASSIGNMENT','PROJECT',"
            "'PRESENTATION','CLASS','TASK','OTHER')",
            name="ck_calendar_events_event_type",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(varchar(128), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Event type for colour coding (EXAM, QUIZ, ASSIGNMENT, etc.)
    event_type: Mapped[str] = mapped_column(
        varchar(16), nullable=False, default=EVENT_OTHER
    )
    # Optional link to a course (NULL for personal tasks)
    course_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )

    user = relationship("User", lazy="raise", passive_deletes=True)
    course = relationship("Course", lazy="raise", passive_deletes=True)

    @property
    def is_all_day(self) -> bool:  # pragma: no cover - tiny helper for the UI
        return self.event_time is None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CalendarEvent id={self.id} {self.title!r} {self.event_date}>"
