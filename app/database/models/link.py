"""University link model - a portal / site the student uses often."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class UniversityLink(TimestampMixin, IdMixin, Base):
    """One bookmark of one student (آموزش یکپارچه، کتابخانه، نمرات، ...).

    Only the URL is stored - Telegram opens it with an inline ``url``
    button, so there is nothing to render locally.
    """

    __tablename__ = "university_links"
    __table_args__ = (
        # keeps javascript:, data: and friends out of the database
        CheckConstraint(
            "url LIKE 'http://%' OR url LIKE 'https://%'",
            name="ck_university_links_url_scheme",
        ),
        Index("ix_university_links_user_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(varchar(64), nullable=False)
    url: Mapped[str] = mapped_column(varchar(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", lazy="raise", passive_deletes=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UniversityLink id={self.id} {self.title!r}>"
