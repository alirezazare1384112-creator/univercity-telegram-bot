"""A channel a student asked the bot to follow for announcements.

Per-user like everything else: every student keeps their own subscription
list (Eitaa or public Telegram channel) and only their inbox receives the
imported posts.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar

# same values as Announcement.source, so a post keeps its platform
CHANNEL_TELEGRAM = "telegram"
CHANNEL_EITAA = "eitaa"
CHANNEL_PLATFORMS: tuple[str, ...] = (CHANNEL_TELEGRAM, CHANNEL_EITAA)

MAX_HANDLE_LENGTH = 128


class UserChannel(TimestampMixin, IdMixin, Base):
    """One subscribed channel of one user (``url`` is the canonical form)."""

    __tablename__ = "user_channels"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('telegram','eitaa')", name="ck_user_channels_platform"
        ),
        UniqueConstraint("user_id", "url", name="uq_user_channels_user_url"),
        Index("ix_user_channels_user_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(varchar(16), nullable=False)
    # canonical page of the channel (https://eitaa.com/x, https://t.me/x)
    url: Mapped[str] = mapped_column(varchar(255), nullable=False)
    # channel username without @ - what the list shows and sync fetches
    handle: Mapped[str] = mapped_column(varchar(MAX_HANDLE_LENGTH), nullable=False)

    user = relationship("User", lazy="raise", passive_deletes=True)

    @property
    def icon(self) -> str:  # pragma: no cover - tiny helper for the UI
        return "📮" if self.platform == CHANNEL_EITAA else "📨"

    @property
    def display(self) -> str:  # pragma: no cover - tiny helper for the UI
        return f"{self.icon} {self.handle}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserChannel id={self.id} {self.handle!r} platform={self.platform}>"
