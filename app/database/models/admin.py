"""Admin model - admin operators are stored separately from normal users."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class Admin(TimestampMixin, IdMixin, Base):
    """Admin panel operator. Completely separated from normal users."""

    __tablename__ = "admins"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(varchar(64))
    first_name: Mapped[str | None] = mapped_column(varchar(128))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Admin id={self.id} telegram_id={self.telegram_id}>"
