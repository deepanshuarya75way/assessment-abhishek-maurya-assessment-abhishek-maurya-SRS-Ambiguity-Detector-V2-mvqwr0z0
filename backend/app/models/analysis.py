"""`analyses` — one analysis run over pasted text or a document (§3.2).

Stage 06 writes: `status='segmented'`, TEXT `source_text` (normalized input —
re-segmentation reproduces identical segments), NULL `score`/`band` (no
detection yet), `ai_status='skipped'`. Stage 07 fills scores + extends the
`status` vocabulary via a new migration.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin, UpdatedMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.issue import Issue
    from app.models.requirement import Requirement
    from app.models.user import User


class Analysis(Base, CreatedMixin, UpdatedMixin):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_analyses_score_range"),
        CheckConstraint(
            "status IN ('segmented', 'analyzed', 'failed')",
            name="ck_analyses_status",
        ),
        CheckConstraint("source_type IN ('text', 'document')", name="ck_analyses_source_type"),
        CheckConstraint(
            "band IN ('low', 'moderate', 'high', 'very_high')", name="ck_analyses_band"
        ),
        CheckConstraint(
            "ai_status IN ('ok', 'failed', 'skipped', 'unconfigured')",
            name="ck_analyses_ai_status",
        ),
        CheckConstraint("requirements_count >= 0", name="ck_analyses_req_count"),
        CheckConstraint("issues_count >= 0", name="ck_analyses_issue_count"),
        Index("ix_analyses_owner_created", "owner_id", "created_at"),
        Index("ix_analyses_owner_score", "owner_id", "score"),
        Index("ix_analyses_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="segmented", server_default="segmented"
    )
    source_text: Mapped[str | None] = mapped_column(Text)  # normalized input (TEXT)
    source_excerpt: Mapped[str | None] = mapped_column(Text)  # app-capped ≤500 chars
    score: Mapped[int | None] = mapped_column(SmallInteger)  # NULL until Stage 07
    band: Mapped[str | None] = mapped_column(String(16))  # NULL until Stage 07
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    requirements_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    issues_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    health: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_overview: Mapped[str | None] = mapped_column(Text)
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    ai_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="skipped", server_default="skipped"
    )
    ai_error: Mapped[str | None] = mapped_column(String(300))

    owner: Mapped["User"] = relationship(back_populates="analyses")
    document: Mapped["Document | None"] = relationship(back_populates="analyses")
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="analysis", passive_deletes=True
    )
    issues: Mapped[list["Issue"]] = relationship(back_populates="analysis", passive_deletes=True)
