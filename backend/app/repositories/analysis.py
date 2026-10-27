"""Analysis + requirement + issue persistence. SQLAlchemy lives here; no rules here.

Ownership arrives from the caller (the service passes the session user id —
never a client-supplied id). Reads are owner-scoped (`get_owned` doubles as
the IDOR guard: no row, no oracle). No commits here: the service's
@transactional boundary owns the transaction.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.document import Document
from app.models.issue import Issue
from app.models.requirement import Requirement

SortKey = Literal["created_at", "-created_at", "score", "-score"]


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so history `q` matches literally (`%`, `_`
    and `\\` in user input are data, never pattern syntax)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class RequirementRow:
    """One requirement to insert (service maps `Segment` + engine output →
    this; the column vocabulary stays in one place and no service type leaks
    into this layer)."""

    position: int
    identifier: str | None
    section: str | None
    text: str
    segmentation: dict[str, Any]
    score: int | None = None
    severity: str | None = None
    issues_count: int = 0


@dataclass(frozen=True)
class IssueRow:
    """One issue to insert. `id` is service-generated (uuid4) so the
    analysis `score_breakdown` can reference issues before they are flushed."""

    id: uuid.UUID
    requirement_id: uuid.UUID
    detector_id: str
    category: str
    severity: str
    phrase: str
    start_offset: int
    end_offset: int
    reason: str
    recommendation: str


@dataclass(frozen=True)
class AnalysisListRow:
    """One history-list row with only response-needed columns.

    Stage 25 deliberately avoids selecting `analyses.source_text` (up to
    200k chars) and detail-only AI/JSON columns for history/recent pages.
    `filename`/`file_type` are None for text analyses AND when the linked
    document row is absent.
    """

    id: uuid.UUID
    title: str
    status: str
    source_type: str
    source_excerpt: str | None
    score: int | None
    band: str | None
    requirements_count: int
    issues_count: int
    created_at: datetime
    updated_at: datetime
    filename: str | None
    file_type: str | None


class AnalysisRepository:
    """`analyses` rows (Stage 07 writes ANALYZED text analyses)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        title: str,
        source_type: str,
        status: str,
        source_text: str,
        source_excerpt: str,
        requirements_count: int,
        issues_count: int,
        document_id: uuid.UUID | None = None,
        score: int | None = None,
        band: str | None = None,
        score_breakdown: dict[str, Any] | None = None,
        health: dict[str, Any] | None = None,
    ) -> Analysis:
        row = Analysis(
            owner_id=owner_id,
            document_id=document_id,
            title=title,
            source_type=source_type,
            status=status,
            source_text=source_text,
            source_excerpt=source_excerpt,
            requirements_count=requirements_count,
            issues_count=issues_count,
            score=score,
            band=band,
            score_breakdown=score_breakdown or {},
            health=health,
        )
        self._session.add(row)
        await self._session.flush()  # surfaces constraint violations inside the txn
        # Server-clock timestamps are readable only after a refresh (client time
        # is never trusted — models/base.py), so the service can return them.
        await self._session.refresh(row)
        return row

    async def get_owned(self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID) -> Analysis | None:
        """One analysis iff owned (None covers missing AND foreign — IDOR)."""
        result = await self._session.execute(
            select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        *,
        owner_id: uuid.UUID,
        offset: int,
        limit: int,
        sort: SortKey,
        band: str | None,
        source_type: str | None,
        q: str | None,
    ) -> tuple[list[AnalysisListRow], int]:
        """Newest-first page of owned analyses + total (contract §3).

        Stage 10: LEFT JOINs the source document's display columns (both
        sides owner-scoped, like the detail's double `get_owned`) and
        optionally filters by `q` — case-insensitive substring over title +
        document filename. `q` arrives normalized + length-capped; LIKE
        wildcards are escaped here. The join is many-to-one, so the total
        stays exact with the same filters applied.
        """
        join_on = (Document.id == Analysis.document_id) & (Document.owner_id == owner_id)
        filters = [Analysis.owner_id == owner_id]
        if band is not None:
            filters.append(Analysis.band == band)
        if source_type is not None:
            filters.append(Analysis.source_type == source_type)
        if q is not None:
            pattern = f"%{_escape_like(q)}%"
            filters.append(
                or_(
                    Analysis.title.ilike(pattern, escape="\\"),
                    Document.filename.ilike(pattern, escape="\\"),
                )
            )
        total = (
            await self._session.execute(
                select(func.count())
                .select_from(Analysis)
                .outerjoin(Document, join_on)
                .where(*filters)
            )
        ).scalar_one()
        order: tuple[Any, ...] = {
            "created_at": (Analysis.created_at.asc(), Analysis.id.asc()),
            "-created_at": (Analysis.created_at.desc(), Analysis.id.desc()),
            "score": (Analysis.score.asc(), Analysis.id.asc()),
            "-score": (Analysis.score.desc(), Analysis.id.desc()),
        }[sort]
        result = await self._session.execute(
            select(
                Analysis.id,
                Analysis.title,
                Analysis.status,
                Analysis.source_type,
                Analysis.source_excerpt,
                Analysis.score,
                Analysis.band,
                Analysis.requirements_count,
                Analysis.issues_count,
                Analysis.created_at,
                Analysis.updated_at,
                Document.filename,
                Document.file_type,
            )
            .outerjoin(Document, join_on)
            .where(*filters)
            .order_by(*order)
            .offset(offset)
            .limit(limit)
        )
        rows = [
            AnalysisListRow(
                id=row[0],
                title=row[1],
                status=row[2],
                source_type=row[3],
                source_excerpt=row[4],
                score=row[5],
                band=row[6],
                requirements_count=row[7],
                issues_count=row[8],
                created_at=row[9],
                updated_at=row[10],
                filename=row[11],
                file_type=row[12],
            )
            for row in result.all()
        ]
        return rows, total

    async def delete(self, row: Analysis) -> None:
        """Delete an owned row (requirements + issues cascade in the DB)."""
        await self._session.delete(row)
        await self._session.flush()

    async def record_ai_result(
        self,
        *,
        owner_id: uuid.UUID,
        analysis_id: uuid.UUID,
        ai_overview: str | None,
        ai_provider: str | None,
        ai_status: str,
        ai_error: str | None,
    ) -> int:
        """Stamp the AI-enhancement outcome on an owned analysis (Stage 14:
        the deterministic row exists already; this UPDATE touches ONLY the
        `ai_*` columns). Returns the affected row count — 0 means the row
        vanished mid-run (concurrent delete); the caller logs, never crashes.
        """
        result = await self._session.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id, Analysis.owner_id == owner_id)
            .values(
                ai_overview=ai_overview,
                ai_provider=ai_provider,
                ai_status=ai_status,
                ai_error=ai_error,
            )
        )
        await self._session.flush()
        # DML `execute()` yields a CursorResult at runtime (SQLAlchemy docs
        # sanction `.rowcount`); the declared `Result` type just doesn't admit it.
        rowcount: int = result.rowcount  # type: ignore[attr-defined]
        return rowcount


class RequirementRepository:
    """`requirements` rows in extraction order (position 0-based, unique)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_many(
        self,
        *,
        owner_id: uuid.UUID,
        analysis_id: uuid.UUID,
        rows: list[RequirementRow],
    ) -> list[Requirement]:
        inserted = [
            Requirement(
                owner_id=owner_id,
                analysis_id=analysis_id,
                position=item.position,
                identifier=item.identifier,
                section=item.section,
                text=item.text,
                segmentation=item.segmentation,
                score=item.score,
                severity=item.severity,
                issues_count=item.issues_count,
            )
            for item in rows
        ]
        self._session.add_all(inserted)
        await self._session.flush()  # one round-trip; UNIQUE violations abort here
        return inserted

    async def list_for_analysis(self, *, analysis_id: uuid.UUID) -> list[Requirement]:
        result = await self._session.execute(
            select(Requirement)
            .where(Requirement.analysis_id == analysis_id)
            .order_by(Requirement.position.asc())
        )
        return list(result.scalars().all())

    async def set_suggested_rewrites(
        self, *, analysis_id: uuid.UUID, rewrites: dict[uuid.UUID, str]
    ) -> None:
        """Stamp AI rewrites on owned-analysis requirements (Stage 14: one
        UPDATE per improved requirement — the caller caps the count, so the
        loop stays bounded; analysis-scoped so a stale id can't cross rows).
        """
        for requirement_id, text in rewrites.items():
            await self._session.execute(
                update(Requirement)
                .where(
                    Requirement.id == requirement_id,
                    Requirement.analysis_id == analysis_id,
                )
                .values(suggested_rewrite=text, suggestion_source="ai")
            )

    async def clear_ai_rewrites(self, *, analysis_id: uuid.UUID) -> None:
        """Drop AI-stamped rewrites for a re-run (Stage 17: `retry-ai` resets
        BEFORE re-running so a failed retry can never strand stale `ok`
        rewrites under a `failed` status. `suggestion_source='ai'` ONLY —
        rule-sourced suggestions are deterministic and never touched)."""
        await self._session.execute(
            update(Requirement)
            .where(
                Requirement.analysis_id == analysis_id,
                Requirement.suggestion_source == "ai",
            )
            .values(suggested_rewrite=None, suggestion_source=None)
        )
        await self._session.flush()
        await self._session.flush()


class IssueRepository:
    """`issues` rows (Stage 07: detector findings with evidence offsets)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_many(
        self,
        *,
        owner_id: uuid.UUID,
        analysis_id: uuid.UUID,
        rows: list[IssueRow],
    ) -> list[Issue]:
        inserted = [
            Issue(
                id=item.id,
                owner_id=owner_id,
                requirement_id=item.requirement_id,
                analysis_id=analysis_id,
                detector_id=item.detector_id,
                category=item.category,
                severity=item.severity,
                phrase=item.phrase,
                start_offset=item.start_offset,
                end_offset=item.end_offset,
                reason=item.reason,
                recommendation=item.recommendation,
            )
            for item in rows
        ]
        self._session.add_all(inserted)
        await self._session.flush()
        return inserted

    async def list_for_analysis(self, *, analysis_id: uuid.UUID) -> list[Issue]:
        """Issues in reading order (requirement position, then span). Spans
        are unique per requirement after engine dedup, so this exactly
        restores finding order — no sequence column needed."""
        result = await self._session.execute(
            select(Issue)
            .join(Requirement, Issue.requirement_id == Requirement.id)
            .where(Issue.analysis_id == analysis_id)
            .order_by(
                Requirement.position.asc(),
                Issue.start_offset.asc(),
                Issue.end_offset.asc(),
            )
        )
        return list(result.scalars().all())
