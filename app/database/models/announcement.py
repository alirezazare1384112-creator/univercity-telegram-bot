"""Announcement model - a university post the student saved from Telegram."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar

# where the post came from; phase 11 = Telegram, phase 12 adds Eitaa
ANNOUNCEMENT_TELEGRAM = "telegram"
ANNOUNCEMENT_EITAA = "eitaa"
ANNOUNCEMENT_SOURCES: tuple[str, ...] = (ANNOUNCEMENT_TELEGRAM, ANNOUNCEMENT_EITAA)

ANNOUNCEMENT_PHOTO = "photo"
ANNOUNCEMENT_DOCUMENT = "document"
ANNOUNCEMENT_FILE_TYPES: tuple[str, ...] = (ANNOUNCEMENT_PHOTO, ANNOUNCEMENT_DOCUMENT)

# Telegram messages are at most 4096 characters long
MAX_TEXT_LENGTH = 4000
MAX_TITLE_LENGTH = 128


class Announcement(TimestampMixin, IdMixin, Base):
    """A forwarded channel post kept as a personal inbox item.

    Per-user like everything else in this bot: every student only ever
    sees their own announcements. Media is stored as a Telegram
    ``file_id`` (no disk usage), same decision as notes and schedule.
    """

    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "source IN ('telegram','eitaa')", name="ck_announcements_source"
        ),
        CheckConstraint(
            "file_type IS NULL OR file_type IN ('photo','document')",
            name="ck_announcements_file_type",
        ),
        Index("ix_announcements_user_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(
        varchar(16), nullable=False, default=ANNOUNCEMENT_TELEGRAM
    )
    # channel title / first line of the post - what buttons show
    title: Mapped[str] = mapped_column(varchar(MAX_TITLE_LENGTH), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    # direct t.me link to the original post when the origin is known
    source_url: Mapped[str | None] = mapped_column(varchar(255))
    file_type: Mapped[str | None] = mapped_column(varchar(16))
    file_id: Mapped[str | None] = mapped_column(varchar(255))

    user = relationship("User", lazy="raise", passive_deletes=True)

    @property
    def is_photo(self) -> bool:  # pragma: no cover - tiny helper for the UI
        return self.file_type == ANNOUNCEMENT_PHOTO

    @property
    def source_icon(self) -> str:  # pragma: no cover - tiny helper for the UI
        return "📨" if self.source == ANNOUNCEMENT_TELEGRAM else "📮"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Announcement id={self.id} {self.title!r} source={self.source}>"
