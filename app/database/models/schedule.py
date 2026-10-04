"""Weekly schedule model - one active photo per student."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class WeeklySchedule(TimestampMixin, IdMixin, Base):
    """Photo of the student's weekly class schedule.

    Telegram ``file_id`` is stored instead of copying the file to disk, so
    resending the schedule needs no upload.
    """

    __tablename__ = "weekly_schedules"
    __table_args__ = (
        # A student can have at most one *active* schedule.
        Index(
            "uq_weekly_schedules_active_user",
            "user_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active IS TRUE"),
        ),
        Index("ix_weekly_schedules_user_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_file_id: Mapped[str] = mapped_column(varchar(255), nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(varchar(255))
    # "photo" or "document" -> decides send_photo vs send_document
    file_type: Mapped[str] = mapped_column(varchar(16), nullable=False, default="photo")
    caption: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user = relationship("User", back_populates="weekly_schedules", lazy="raise")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WeeklySchedule id={self.id} user_id={self.user_id} active={self.is_active}>"
