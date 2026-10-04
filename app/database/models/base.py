"""SQLAlchemy declarative base, common mixins and shared column types."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Timezone aware UTC instant stored as a naive UTC datetime.

    All datetimes in the database are naive UTC. Conversion to the bot
    timezone (see ``TIMEZONE`` in ``.env``) happens only in the UI layer.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Base class for every ORM model."""


class TimestampMixin:
    """``created_at`` / ``updated_at`` maintained by Python (not the DB)
    so SQLite and PostgreSQL behave exactly the same way."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class IdMixin:
    """Surrogate primary key."""

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)


def varchar(length: int) -> String:
    """Small helper so every string column declares a max length."""
    return String(length)
