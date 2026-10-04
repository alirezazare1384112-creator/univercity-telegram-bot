"""Course model - the courses of one student in one semester."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class Course(TimestampMixin, IdMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (CheckConstraint("units > 0", name="ck_courses_units_positive"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(varchar(128), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    teacher_name: Mapped[str | None] = mapped_column(varchar(128))
    semester: Mapped[str | None] = mapped_column(varchar(64))
    academic_year: Mapped[str | None] = mapped_column(varchar(32))

    user = relationship("User", back_populates="courses", lazy="raise", passive_deletes=True)
    grade_items = relationship(
        "GradeItem", back_populates="course", lazy="raise", passive_deletes=True
    )

    @property
    def title(self) -> str:
        return f"{self.name} ({self.units} واحد)"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Course id={self.id} name={self.name!r} units={self.units}>"
