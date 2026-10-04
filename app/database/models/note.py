"""Note model - a study file (PDF, image, ...) saved by a student."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar

# what Telegram handed us; decides send_photo vs send_document
NOTE_PHOTO = "photo"
NOTE_DOCUMENT = "document"
NOTE_FILE_TYPES: tuple[str, ...] = (NOTE_PHOTO, NOTE_DOCUMENT)


class Note(TimestampMixin, IdMixin, Base):
    """A lecture note / file.

    Only the Telegram ``file_id`` is stored (same decision as the weekly
    schedule): the file itself stays on Telegram's servers, so saving and
    re-sending needs no upload, no disk space and no backup.
    """

    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("file_type IN ('photo','document')", name="ck_notes_file_type"),
        Index("ix_notes_user_id", "user_id"),
        Index("ix_notes_course_id", "course_id"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # nullable: a note can exist before/without a course (SET NULL keeps it)
    course_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(varchar(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(
        varchar(16), nullable=False, default=NOTE_DOCUMENT
    )
    file_id: Mapped[str] = mapped_column(varchar(255), nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(varchar(255))
    # original filename of documents ("file_name.pdf")
    file_name: Mapped[str | None] = mapped_column(varchar(255))

    user = relationship("User", lazy="raise", passive_deletes=True)
    course = relationship("Course", lazy="raise", passive_deletes=True)

    @property
    def is_photo(self) -> bool:  # pragma: no cover - tiny helper for the UI
        return self.file_type == NOTE_PHOTO

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Note id={self.id} {self.title!r} type={self.file_type}>"
