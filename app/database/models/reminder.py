"""Reminder and reminder notification models."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar

# --- repeat types -------------------------------------------------------
REPEAT_NONE = "NONE"
REPEAT_DAILY = "DAILY"
REPEAT_WEEKLY = "WEEKLY"
REPEAT_MONTHLY = "MONTHLY"
REPEAT_TYPES: tuple[str, ...] = (REPEAT_NONE, REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_MONTHLY)

REPEAT_LABELS: dict[str, str] = {
    REPEAT_NONE: "بدون تکرار",
    REPEAT_DAILY: "هر روز",
    REPEAT_WEEKLY: "هر هفته",
    REPEAT_MONTHLY: "هر ماه",
}

# --- alert offsets ------------------------------------------------------
ALERT_AT_TIME = "AT_TIME"     # right at the event
ALERT_HOURS_1 = "HOURS_1"     # one hour before
ALERT_DAYS_1 = "DAYS_1"       # one day before
ALERT_OFFSETS: tuple[str, ...] = (ALERT_AT_TIME, ALERT_HOURS_1, ALERT_DAYS_1)

ALERT_LABELS: dict[str, str] = {
    ALERT_AT_TIME: "🔔 در زمان رویداد",
    ALERT_HOURS_1: "⏱ ۱ ساعت قبل",
    ALERT_DAYS_1: "📆 ۱ روز قبل",
}

# timedelta subtraction is done in the service, keeping this module ORM only
ALERT_TDELTA_HOURS: dict[str, int] = {
    ALERT_AT_TIME: 0,
    ALERT_HOURS_1: 1,
    ALERT_DAYS_1: 24,
}


class Reminder(TimestampMixin, IdMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(
            "repeat_type IN ('NONE','DAILY','WEEKLY','MONTHLY')",
            name="ck_reminders_repeat_type",
        ),
        Index("ix_reminders_reminder_datetime", "reminder_datetime"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(varchar(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # naive UTC
    reminder_datetime: Mapped[object] = mapped_column(DateTime, nullable=False)
    repeat_type: Mapped[str] = mapped_column(
        varchar(16), nullable=False, default=REPEAT_NONE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    notifications = relationship(
        "ReminderNotification",
        back_populates="reminder",
        lazy="raise",
        passive_deletes=True,
    )
    user = relationship("User", lazy="raise", passive_deletes=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reminder id={self.id} {self.title!r} at={self.reminder_datetime}>"


class ReminderNotification(TimestampMixin, IdMixin, Base):
    """One pending alert of one occurrence of a reminder.

    A reminder with three alerts and no repeat has exactly three rows,
    all with ``is_sent = FALSE`` until the scheduler delivers them.
    """

    __tablename__ = "reminder_notifications"
    __table_args__ = (
        CheckConstraint(
            "alert_offset IN ('AT_TIME','HOURS_1','DAYS_1')",
            name="ck_reminder_notifications_alert_offset",
        ),
        UniqueConstraint(
            "reminder_id",
            "alert_offset",
            "fire_datetime",
            name="uq_reminder_notifications_occurrence",
        ),
        Index("ix_reminder_notifications_due", "is_sent", "fire_datetime"),
    )

    reminder_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("reminders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_offset: Mapped[str] = mapped_column(varchar(16), nullable=False)
    # naive UTC moment when this alert must be sent
    fire_datetime: Mapped[object] = mapped_column(DateTime, nullable=False)
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)

    reminder = relationship("Reminder", back_populates="notifications")

    @property
    def is_due(self) -> bool:  # pragma: no cover - convenience
        from app.utils.datetime_utils import utcnow_naive

        return (not self.is_sent) and self.fire_datetime <= utcnow_naive()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReminderNotification reminder={self.reminder_id} "
            f"{self.alert_offset} at={self.fire_datetime} sent={self.is_sent}>"
        )
