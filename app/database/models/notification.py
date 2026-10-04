"""Notification log - audit trail for every automatic message."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, IdMixin, utcnow, varchar

# notification types
TYPE_REMINDER = "REMINDER"
TYPE_ANNOUNCEMENT = "ANNOUNCEMENT"
TYPE_BROADCAST = "BROADCAST"
NOTIFICATION_TYPES: tuple[str, ...] = (TYPE_REMINDER, TYPE_ANNOUNCEMENT, TYPE_BROADCAST)

# delivery status
STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"
NOTIFICATION_STATUSES: tuple[str, ...] = (STATUS_SENT, STATUS_FAILED)


class NotificationLog(IdMixin, Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SENT','FAILED')", name="ck_notification_logs_status"
        ),
        CheckConstraint(
            "notification_type IN ('REMINDER','ANNOUNCEMENT','BROADCAST')",
            name="ck_notification_logs_notification_type",
        ),
        Index("ix_notification_logs_related", "notification_type", "related_id"),
    )

    # SET NULL: a log must survive the deletion of its user
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notification_type: Mapped[str] = mapped_column(varchar(32), nullable=False)
    related_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(varchar(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotificationLog {self.notification_type} {self.status}>"
