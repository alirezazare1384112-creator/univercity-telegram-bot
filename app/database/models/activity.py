"""WeeklyActivity model - a planned recurring activity per weekday.

The "Activity Room" is a personal weekly planner: the student says
"Saturday 14:00 — gym, 1.5 h", "Sunday 09:00 — study calculus, 2 h".
Unlike ``CalendarEvent`` (a dated appointment), this is a *recurring*
template that the same day every week shows the same block.
"""

from __future__ import annotations

from datetime import time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar

# Day numbering follows the Persian week, which starts on Saturday.
# 1 = Saturday, 2 = Sunday, ..., 7 = Friday.
ACTIVITY_DAY_SAT = 1
ACTIVITY_DAY_SUN = 2
ACTIVITY_DAY_MON = 3
ACTIVITY_DAY_TUE = 4
ACTIVITY_DAY_WED = 5
ACTIVITY_DAY_THU = 6
ACTIVITY_DAY_FRI = 7
ACTIVITY_DAYS: tuple[int, ...] = (
    ACTIVITY_DAY_SAT,
    ACTIVITY_DAY_SUN,
    ACTIVITY_DAY_MON,
    ACTIVITY_DAY_TUE,
    ACTIVITY_DAY_WED,
    ACTIVITY_DAY_THU,
    ACTIVITY_DAY_FRI,
)

# Categories for colour coding the planner blocks.
ACTIVITY_STUDY = "STUDY"
ACTIVITY_SPORT = "SPORT"
ACTIVITY_REST = "REST"
ACTIVITY_WORK = "WORK"
ACTIVITY_PERSONAL = "PERSONAL"
ACTIVITY_OTHER = "OTHER"
ACTIVITY_CATEGORIES: tuple[str, ...] = (
    ACTIVITY_STUDY,
    ACTIVITY_SPORT,
    ACTIVITY_REST,
    ACTIVITY_WORK,
    ACTIVITY_PERSONAL,
    ACTIVITY_OTHER,
)

ACTIVITY_CATEGORY_LABELS: dict[str, str] = {
    ACTIVITY_STUDY: "مطالعه",
    ACTIVITY_SPORT: "ورزش",
    ACTIVITY_REST: "استراحت",
    ACTIVITY_WORK: "کار",
    ACTIVITY_PERSONAL: "شخصی",
    ACTIVITY_OTHER: "سایر",
}


class WeeklyActivity(TimestampMixin, IdMixin, Base):
    """One recurring block in the personal weekly planner.

    ``day_of_week`` is 1..7 (Saturday..Friday). ``start_time`` is the
    wall-clock start in the student's local timezone (no conversion —
    a planner block is not a UTC instant). ``duration_hours`` may be
    fractional (1.5 = 90 minutes).
    """

    __tablename__ = "weekly_activities"
    __table_args__ = (
        Index("ix_weekly_activities_user_id", "user_id"),
        Index("ix_weekly_activities_day", "day_of_week"),
        CheckConstraint(
            "day_of_week BETWEEN 1 AND 7", name="ck_weekly_activities_day_of_week"
        ),
        CheckConstraint(
            "duration_hours > 0 AND duration_hours <= 24",
            name="ck_weekly_activities_duration",
        ),
        CheckConstraint(
            "category IN ('STUDY','SPORT','REST','WORK','PERSONAL','OTHER')",
            name="ck_weekly_activities_category",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(varchar(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 1=Saturday ... 7=Friday
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_hours: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    category: Mapped[str] = mapped_column(
        varchar(16), nullable=False, default=ACTIVITY_OTHER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user = relationship("User", lazy="raise", passive_deletes=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<WeeklyActivity id={self.id} day={self.day_of_week} "
            f"{self.start_time} {self.title!r}>"
        )
