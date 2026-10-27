"""`ai_provider_credentials` — per-user ENCRYPTED provider keys (§3.6).

Plaintext MUST NEVER touch this table: `encrypted_api_key` holds Fernet ciphertext
(`vN:`-prefixed) produced by the backend vault (Stage 17). Only `last4` +
`key_fingerprint` ever leave the database toward the frontend/logs.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin, UpdatedMixin

if TYPE_CHECKING:
    from app.models.user import User


class AICredential(Base, CreatedMixin, UpdatedMixin):
    __tablename__ = "ai_provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "provider",
            "key_fingerprint",
            name="uq_ai_cred_owner_provider_fingerprint",
        ),
        CheckConstraint(
            "provider IN ('gemini', 'groq', 'openai', 'anthropic', 'openrouter'," " 'huggingface')",
            name="ck_ai_cred_provider",
        ),
        CheckConstraint("key_version >= 1", name="ck_ai_cred_key_version"),
        CheckConstraint("fallback_rank >= 0", name="ck_ai_cred_fallback_rank"),
        CheckConstraint("last_test_status IN ('ok', 'failed')", name="ck_ai_cred_test_status"),
        Index("ix_ai_cred_owner_fallback", "owner_id", "fallback_rank"),
        # Exactly one default per owner; at most one ENABLED key per owner+provider.
        Index(
            "uq_ai_cred_default_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index(
            "uq_ai_cred_enabled_per_provider",
            "owner_id",
            "provider",
            unique=True,
            postgresql_where=text("is_enabled"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str | None] = mapped_column(String(80))
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    key_fingerprint: Mapped[str] = mapped_column(CHAR(16), nullable=False)
    last4: Mapped[str] = mapped_column(CHAR(4), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    fallback_rank: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    last_tested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_status: Mapped[str | None] = mapped_column(String(16))

    owner: Mapped["User"] = relationship(back_populates="ai_credentials")
