"""`documents` — uploaded file METADATA only (§3.5).

Binaries live in object storage (Supabase Storage), never in Postgres.
`storage_path` is a server-generated opaque key (never user input, never exposed).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.user import User


class Document(Base, CreatedMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_path", name="uq_documents_storage_path"),
        CheckConstraint("byte_size >= 0", name="ck_documents_byte_size"),
        CheckConstraint("extracted_chars >= 0", name="ck_documents_extracted_chars"),
        CheckConstraint(
            "extraction_status IN ('pending', 'ok', 'failed')",
            name="ck_documents_extraction_status",
        ),
        CheckConstraint(
            "file_type IN ('pdf', 'docx', 'txt')",
            name="ck_documents_file_type",
        ),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(8))  # verified type (0005)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_chars: Mapped[int | None] = mapped_column()
    extraction_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )

    owner: Mapped["User"] = relationship(back_populates="documents")
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="document", passive_deletes=True
    )
