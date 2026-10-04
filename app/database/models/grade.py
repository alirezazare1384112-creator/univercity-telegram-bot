"""Grade item model - one scored component of a course."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class GradeItem(TimestampMixin, IdMixin, Base):
    """Example: \"میان‌ترم: 6 از 8\", \"تمرین 1: 1.5 از 2\".

    ``Float`` is used instead of ``Decimal`` so SQLite and PostgreSQL
    behave exactly the same way (grades never need decimal money
    precision).
    """

    __tablename__ = "grade_items"
    __table_args__ = (
        CheckConstraint("score >= 0", name="ck_grade_items_score_positive"),
        CheckConstraint("max_score > 0", name="ck_grade_items_max_score_positive"),
        CheckConstraint("score <= max_score", name="ck_grade_items_score_lte_max"),
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(varchar(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    description: Mapped[str | None] = mapped_column(Text)

    course = relationship("Course", back_populates="grade_items", lazy="raise", passive_deletes=True)

    @property
    def percent(self) -> float:
        if not self.max_score:
            return 0.0
        return round(self.score / self.max_score * 100, 1)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GradeItem id={self.id} {self.title!r} {self.score}/{self.max_score}>"
