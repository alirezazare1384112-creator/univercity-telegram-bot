"""User and Admin models."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class User(TimestampMixin, IdMixin, Base):
    """Every Telegram account that started the bot."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(varchar(64))
    first_name: Mapped[str | None] = mapped_column(varchar(128))
    last_name: Mapped[str | None] = mapped_column(varchar(128))
    # Telegram profile photo URL sent in initData (when the user has one).
    # Null when the user has no profile photo or the field is not present.
    # Telegram signs this URL inside initData so it is safe to trust.
    photo_url: Mapped[str | None] = mapped_column(varchar(512))

    # Profile (optional, filled by the user from the profile menu)
    student_number: Mapped[str | None] = mapped_column(varchar(32), index=True)
    field_of_study: Mapped[str | None] = mapped_column(varchar(128))
    university: Mapped[str | None] = mapped_column(varchar(128))
    semester: Mapped[str | None] = mapped_column(varchar(64))

    bio: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    # Children are removed by the database (ON DELETE CASCADE).
    # ``passive_deletes`` lets SQLAlchemy skip loading them and
    # ``lazy="raise"`` makes an accidental eager load fail loudly.
    weekly_schedules = relationship(
        "WeeklySchedule", back_populates="user", lazy="raise", passive_deletes=True
    )
    courses = relationship(
        "Course", back_populates="user", lazy="raise", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<User id={self.id} telegram_id={self.telegram_id}>"
