"""University link model - a portal / site the student uses often."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IdMixin, TimestampMixin, varchar


class UniversityLink(TimestampMixin, IdMixin, Base):
    """One bookmark of one student (آموزش یکپارچه، کتابخانه، نمرات، ...).

    Optional credentials (``ciphertext_b64`` + ``wrapped_key_b64``) store
    a username/password pair for auto-login. Both fields are
    AES-GCM-encrypted via envelope encryption (see
    ``app.utils.credentials``); the plaintext never touches the database.
    Both are NULL when the user has not saved a login for this link.
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

    # Encrypted credential payload (base64 of ``nonce || ct || tag``).
    # NULL when no credential is stored.
    ciphertext_b64: Mapped[str | None] = mapped_column(Text)
    # Encrypted data key (base64 of ``nonce || wrapped_key``).
    # NULL when no credential is stored; must be set iff ciphertext_b64 is.
    wrapped_key_b64: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", lazy="raise", passive_deletes=True)

    @property
    def has_credentials(self) -> bool:
        return bool(self.ciphertext_b64) and bool(self.wrapped_key_b64)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UniversityLink id={self.id} {self.title!r}>"
