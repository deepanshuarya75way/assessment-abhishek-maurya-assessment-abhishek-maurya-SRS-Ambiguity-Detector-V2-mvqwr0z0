"""`users` — accounts and future auth anchor (the project contract).

Auth behavior lands in later stages; this stage only creates the persistence shape.
`password_hash` holds an argon2id hash (Stage 04) — NEVER plaintext. NULL reserves a
future external identity provider; local accounts always set it (enforced app-side).
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin, UpdatedMixin

if TYPE_CHECKING:  # runtime resolution is by registry name (no import cycle)
    from app.models.ai_credential import AICredential
    from app.models.analysis import Analysis
    from app.models.auth_tokens import (
        PasswordResetToken,
        RefreshToken,
    )
    from app.models.document import Document
    from app.models.user_preference import UserPreference


class User(Base, CreatedMixin, UpdatedMixin):
    __tablename__ = "users"
    __table_args__ = (
        # One external subject maps to one account (NULLs — i.e. local users — exempt).
        Index(
            "ix_users_idp_subject",
            "identity_provider",
            "external_subject",
            unique=True,
            postgresql_where=text("external_subject IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # UNIQUE implies an index (auth lookup path). App lowercases before persist.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str | None] = mapped_column(Text)
    identity_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local", server_default="local"
    )
    external_subject: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # DB cascades own deletion (passive_deletes: ORM never SELECTs children to delete).
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="owner", passive_deletes=True)
    documents: Mapped[list["Document"]] = relationship(back_populates="owner", passive_deletes=True)
    ai_credentials: Mapped[list["AICredential"]] = relationship(
        back_populates="owner", passive_deletes=True
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="owner", passive_deletes=True
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="owner", passive_deletes=True
    )
    preferences: Mapped["UserPreference | None"] = relationship(
        back_populates="owner", passive_deletes=True
    )
