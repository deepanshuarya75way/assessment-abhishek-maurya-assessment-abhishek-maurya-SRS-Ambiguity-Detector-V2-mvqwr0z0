"""`issues` — one ambiguity finding with evidence offsets (§3.4).

`detector_id` is the stable rule reference behind "Why was this flagged?".
`analysis_id` is denormalized for trend/category queries without joining.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.requirement import Requirement


class Issue(Base, CreatedMixin):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_issues_severity"
        ),
        CheckConstraint("start_offset >= 0", name="ck_issues_start_offset"),
        CheckConstraint("end_offset > start_offset", name="ck_issues_offset_order"),
        Index("ix_issues_analysis_severity", "analysis_id", "severity"),
        Index("ix_issues_analysis_category", "analysis_id", "category"),
        Index("ix_issues_requirement", "requirement_id"),
        Index("ix_issues_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    detector_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    ai_explanation: Mapped[str | None] = mapped_column(Text)

    requirement: Mapped["Requirement"] = relationship(back_populates="issues")
    analysis: Mapped["Analysis"] = relationship(back_populates="issues")
