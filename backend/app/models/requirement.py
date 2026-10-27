"""`requirements` — segmented requirements in extraction order (§3.3).

`position` (0-based, unique per analysis) preserves SRS order. `severity` is the
denormalized worst-of-issues severity (NULL = no issues) for list filtering.
Stage 06 writes: `text` WITHOUT the source marker prefix (identifier stored
separately), NULL `score` (unscored until Stage 07), heading-derived `section`
path, and the `segmentation` JSONB evidence block (strategy, confidence,
offsets, line refs).
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.issue import Issue


class Requirement(Base, CreatedMixin):
    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("analysis_id", "position", name="uq_requirements_analysis_position"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_requirements_score_range"),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_requirements_severity",
        ),
        CheckConstraint("issues_count >= 0", name="ck_requirements_issue_count"),
        CheckConstraint(
            "suggestion_source IN ('rule', 'ai')", name="ck_requirements_suggestion_source"
        ),
        Index("ix_requirements_owner_analysis", "owner_id", "analysis_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Deliberately redundant: ownership check without joining analyses.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    identifier: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    section: Mapped[str | None] = mapped_column(String(200))
    segmentation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    severity: Mapped[str | None] = mapped_column(String(16))
    issues_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    suggested_rewrite: Mapped[str | None] = mapped_column(Text)
    suggestion_source: Mapped[str | None] = mapped_column(String(16))

    analysis: Mapped["Analysis"] = relationship(back_populates="requirements")
    issues: Mapped[list["Issue"]] = relationship(back_populates="requirement", passive_deletes=True)
