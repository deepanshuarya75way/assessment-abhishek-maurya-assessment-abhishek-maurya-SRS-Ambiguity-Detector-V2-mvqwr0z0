"""Auth-token tables (the project contract, Alembic revision `0002`).

Every token column stores the sha256 hex of a 256-bit random value — raw tokens
exist ONLY inside emailed links and request bodies, never at rest, never in logs.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin

if TYPE_CHECKING:  # runtime resolution is by registry name (no import cycle)
    from app.models.user import User


class RefreshToken(Base, CreatedMixin):
    """Rotating refresh sessions. Reuse detection via `replaced_by_hash`:
    presenting a rotated (replaced) token revokes the whole family (theft signal);
    presenting a logged-out (revoked, never replaced) token is a plain 401."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_owner", "owner_id"),
        Index("ix_refresh_tokens_family", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, default=uuid.uuid4)
    replaced_by_hash: Mapped[str | None] = mapped_column(CHAR(64))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_hash: Mapped[str | None] = mapped_column(CHAR(64))

    owner: Mapped["User"] = relationship(back_populates="refresh_tokens")


class PasswordResetToken(Base, CreatedMixin):
    """Single-use password-reset tokens (`consumed_at` set on success)."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_tokens_owner", "owner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped["User"] = relationship(back_populates="password_reset_tokens")
