"""Analysis business logic (API_CONTRACT §4.3; Stage 08: TEXT + DOCUMENT share
`analyze_text`).

Pure of HTTP: takes a session + plain values, returns plain dataclasses (the
router maps them to response schemas). Creation is one deterministic
transaction: validate → normalize → segment → run the engine → persist
analysis + requirements + issues → commit; the TEXT entry point then runs
the OPTIONAL AI step outside any transaction (Stage 14 — the enhancement
service owns that call, this module never touches providers directly).
Reads are owner-scoped (missing and foreign ids are indistinguishable —
the IDOR rule).

Logs carry ids + counts only — raw SRS text is NEVER logged (SECURITY_SPEC
§2.5: requirement text is sensitive content).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import (
    DEDUCTIONS,
    analyze_requirement,
    band_for_score,
    health_for_findings,
    overall_score,
    severity_counts,
)
from app.core.logging import get_logger
from app.exceptions import (
    DocumentAnalysisUnavailableError,
    NoRequirementsDetectedError,
    NotFoundError,
    TextTooLargeError,
)
from app.repositories.analysis import (
    AnalysisRepository,
    IssueRepository,
    IssueRow,
    RequirementRepository,
    RequirementRow,
    SortKey,
)
from app.repositories.documents import DocumentRepository
from app.services.segmentation import (
    MAX_REQUIREMENTS,
    normalize_text,
    segment_requirements,
)
from app.services.transactions import transactional
from app.storage import get_storage_backend

logger = get_logger(__name__)

# Deterministic fallback when the client sends no (or a blank) title.
UNTITLED_TITLE = "Untitled SRS Analysis"
# History-list excerpt of the normalized input (contract: ≤500 chars).
SOURCE_EXCERPT_CHARS = 500


@dataclass(frozen=True)
class IssueDetail:
    """One persisted finding, JSON-safe. `ai_explanation` is always None —
    no ABC method produces per-issue explanations yet (the Stage 14
    enhancement fills overviews + rewrites only; never fabricated)."""

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
    ai_explanation: None = None


@dataclass(frozen=True)
class RequirementDetail:
    """One persisted requirement with its nested issues in span order.
    `suggested_rewrite` is None until the Stage 14 AI enhancement stamps one
    (`suggestion_source='ai'`); rule rewrites would use `'rule'` — the
    original `text` is never modified, rewrites are additive-only."""

    id: uuid.UUID
    position: int
    identifier: str | None
    section: str | None
    text: str
    segmentation: dict[str, Any]
    score: int | None
    severity: str | None
    issues_count: int
    suggested_rewrite: str | None = None
    suggestion_source: str | None = None
    issues: tuple[IssueDetail, ...] = ()


@dataclass(frozen=True)
class DocumentRef:
    """Source-document display pointer (Stage 09): filename + validated type
    for `source_type == "document"` details. No id (no UI link needs it)."""

    filename: str
    file_type: str


@dataclass(frozen=True)
class AnalysisDetail:
    """One persisted analysis with its requirements (+ nested issues).

    `ai_*` mirror the row's enhancement outcome (Stage 14): fresh
    deterministic details read the `skipped`/NULL defaults; `replace` stamps
    real outcomes after the AI step (the enhancement service owns that).
    """

    id: uuid.UUID
    title: str
    status: str
    source_type: str
    score: int | None
    band: str | None
    score_breakdown: dict[str, Any]
    health: dict[str, Any] | None
    requirements_count: int
    issues_count: int
    created_at: datetime
    updated_at: datetime
    requirements: tuple[RequirementDetail, ...]
    document: DocumentRef | None = None
    ai_overview: str | None = None
    ai_provider: str | None = None
    ai_status: str = "skipped"
    ai_error: str | None = None


@dataclass(frozen=True)
class AnalysisSummary:
    """History-list row: detail minus `requirements`, plus `source_excerpt`.
    Stage 10: carries the `document` display pointer (like the detail)."""

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
    document: DocumentRef | None = None


async def create_text_analysis(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    title: str | None,
    text: str,
    document_id: uuid.UUID | None,
    ai_enhance: bool,
) -> AnalysisDetail:
    """TEXT entry point: reject by-id analysis, persist the deterministic
    pipeline in ONE transaction (partial analyses are impossible), THEN run
    the optional AI step outside any transaction (Stage 14: no txn may span
    provider network I/O — the AI outcome commits in its own short txn)."""
    if document_id is not None:
        raise DocumentAnalysisUnavailableError()
    detail = await _persist_text_analysis(
        session,
        owner_id=owner_id,
        title=title,
        text=text,
    )
    # Lazy import: ai_enhancement owns AnalysisDetail from THIS module — a
    # top-level import would cycle. The seam stays one function call.
    from app.services.ai_enhancement import enhance_analysis

    return await enhance_analysis(session, owner_id=owner_id, detail=detail, ai_enhance=ai_enhance)


@transactional
async def _persist_text_analysis(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    title: str | None,
    text: str,
) -> AnalysisDetail:
    """Deterministic TEXT persist (the commit `create_text_analysis` returns
    from before any provider call runs)."""
    return await analyze_text(
        session,
        owner_id=owner_id,
        title=title,
        text=text,
        source_type="text",
        document_id=None,
    )


async def analyze_text(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    title: str | None,
    text: str,
    source_type: str,
    document_id: uuid.UUID | None,
) -> AnalysisDetail:
    """Shared pipeline (TEXT + DOCUMENT): normalize → segment → detect →
    score → persist. No transaction of its own — the CALLER owns the boundary
    (text creation, document upload). Same text ⇒ same findings and scores,
    whatever the source (the Stage 08 equivalence guarantee — no second
    detector, no duplicated segmentation)."""
    normalized = normalize_text(text)
    if not normalized:
        raise NoRequirementsDetectedError()
    segments = segment_requirements(normalized)
    if not segments:
        raise NoRequirementsDetectedError()
    if len(segments) > MAX_REQUIREMENTS:
        raise TextTooLargeError(len(segments), MAX_REQUIREMENTS)

    # Deterministic engine: same segments → same findings, scores, band.
    # Issue ids are generated up front so `score_breakdown` can reference them
    # before anything is flushed (single pass, no post-hoc UPDATE).
    scored = [analyze_requirement(segment.text) for segment in segments]
    all_findings = [finding for result in scored for finding in result.findings]
    issue_ids = [uuid.uuid4() for _ in all_findings]
    overall = overall_score([result.score for result in scored])
    breakdown: dict[str, Any] = {
        "base": 100,
        "deductions": [
            {
                "issue_id": str(issue_id),
                "severity": finding.severity,
                "points": DEDUCTIONS[finding.severity],
            }
            for issue_id, finding in zip(issue_ids, all_findings, strict=True)
        ],
        "counts": severity_counts(all_findings),
    }

    analysis = await AnalysisRepository(session).create(
        owner_id=owner_id,
        title=title or UNTITLED_TITLE,
        source_type=source_type,
        document_id=document_id,
        status="analyzed",
        source_text=normalized,
        source_excerpt=normalized[:SOURCE_EXCERPT_CHARS],
        requirements_count=len(segments),
        issues_count=len(all_findings),
        score=overall,
        band=band_for_score(overall),
        score_breakdown=breakdown,
        health=health_for_findings(all_findings),
    )
    rows = await RequirementRepository(session).create_many(
        owner_id=owner_id,
        analysis_id=analysis.id,
        rows=[
            RequirementRow(
                position=position,
                identifier=segment.identifier,
                section=segment.section,
                text=segment.text,
                segmentation={
                    "strategy": segment.strategy,
                    "confidence": segment.confidence,
                    "start_offset": segment.start_offset,
                    "end_offset": segment.end_offset,
                    "line_start": segment.line_start,
                    "line_end": segment.line_end,
                },
                score=result.score,
                severity=result.severity,
                issues_count=len(result.findings),
            )
            for position, (segment, result) in enumerate(zip(segments, scored, strict=True))
        ],
    )
    issue_rows: list[IssueRow] = []
    nested: list[list[IssueDetail]] = []
    cursor = 0
    for row, result in zip(rows, scored, strict=True):
        details: list[IssueDetail] = []
        for finding in result.findings:
            issue_id = issue_ids[cursor]
            issue_rows.append(
                IssueRow(
                    id=issue_id,
                    requirement_id=row.id,
                    detector_id=finding.detector_id,
                    category=finding.category,
                    severity=finding.severity,
                    phrase=finding.phrase,
                    start_offset=finding.start_offset,
                    end_offset=finding.end_offset,
                    reason=finding.reason,
                    recommendation=finding.recommendation,
                )
            )
            details.append(
                IssueDetail(
                    id=issue_id,
                    requirement_id=row.id,
                    detector_id=finding.detector_id,
                    category=finding.category,
                    severity=finding.severity,
                    phrase=finding.phrase,
                    start_offset=finding.start_offset,
                    end_offset=finding.end_offset,
                    reason=finding.reason,
                    recommendation=finding.recommendation,
                )
            )
            cursor += 1
        nested.append(details)
    await IssueRepository(session).create_many(
        owner_id=owner_id, analysis_id=analysis.id, rows=issue_rows
    )
    logger.info(
        "analysis created analysis_id=%s owner_id=%s requirements=%d issues=%d score=%d",
        analysis.id,
        owner_id,
        len(segments),
        len(all_findings),
        overall,
        extra={"analysis_stage": "deterministic"},
    )
    return AnalysisDetail(
        id=analysis.id,
        title=analysis.title,
        status=analysis.status,
        source_type=analysis.source_type,
        score=analysis.score,
        band=analysis.band,
        score_breakdown=dict(analysis.score_breakdown or {}),
        health=dict(analysis.health) if analysis.health is not None else None,
        requirements_count=analysis.requirements_count,
        issues_count=analysis.issues_count,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        requirements=tuple(
            RequirementDetail(
                id=row.id,
                position=row.position,
                identifier=row.identifier,
                section=row.section,
                text=row.text,
                segmentation=dict(row.segmentation or {}),
                score=row.score,
                severity=row.severity,
                issues_count=row.issues_count,
                issues=tuple(nested[position]),
            )
            for position, row in enumerate(rows)
        ),
    )


async def get_analysis_detail(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> AnalysisDetail:
    """One owned analysis with requirements + nested issues (404 otherwise).
    Read-only: no transaction boundary needed (nothing to commit)."""
    analysis = await AnalysisRepository(session).get_owned(
        owner_id=owner_id, analysis_id=analysis_id
    )
    if analysis is None:
        raise NotFoundError("analysis")
    requirements = await RequirementRepository(session).list_for_analysis(analysis_id=analysis.id)
    issues = await IssueRepository(session).list_for_analysis(analysis_id=analysis.id)
    document: DocumentRef | None = None
    if analysis.document_id is not None:
        # Fourth query ONLY for document analyses (text details cost nothing
        # extra): owner-scoped, so a forged link reads as missing, never leaks.
        doc = await DocumentRepository(session).get_owned(
            owner_id=owner_id, document_id=analysis.document_id
        )
        if doc is not None:
            assert doc.file_type is not None  # Stage 08 writes it NOT NULL
            document = DocumentRef(filename=doc.filename, file_type=doc.file_type)
    by_requirement: dict[uuid.UUID, list[IssueDetail]] = {row.id: [] for row in requirements}
    for issue in issues:
        by_requirement[issue.requirement_id].append(
            IssueDetail(
                id=issue.id,
                requirement_id=issue.requirement_id,
                detector_id=issue.detector_id,
                category=issue.category,
                severity=issue.severity,
                phrase=issue.phrase,
                start_offset=issue.start_offset,
                end_offset=issue.end_offset,
                reason=issue.reason,
                recommendation=issue.recommendation,
            )
        )
    return AnalysisDetail(
        id=analysis.id,
        title=analysis.title,
        status=analysis.status,
        source_type=analysis.source_type,
        score=analysis.score,
        band=analysis.band,
        score_breakdown=dict(analysis.score_breakdown or {}),
        health=dict(analysis.health) if analysis.health is not None else None,
        requirements_count=analysis.requirements_count,
        issues_count=analysis.issues_count,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        requirements=tuple(
            RequirementDetail(
                id=row.id,
                position=row.position,
                identifier=row.identifier,
                section=row.section,
                text=row.text,
                segmentation=dict(row.segmentation or {}),
                score=row.score,
                severity=row.severity,
                issues_count=row.issues_count,
                suggested_rewrite=row.suggested_rewrite,
                suggestion_source=row.suggestion_source,
                issues=tuple(by_requirement[row.id]),
            )
            for row in requirements
        ),
        document=document,
        ai_overview=analysis.ai_overview,
        ai_provider=analysis.ai_provider,
        ai_status=analysis.ai_status,
        ai_error=analysis.ai_error,
    )


async def list_analyses(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    page: int,
    page_size: int,
    sort: SortKey,
    band: str | None,
    source_type: str | None,
    q: str | None,
) -> tuple[list[AnalysisSummary], int]:
    """Newest-first page of owned analyses + total (contract §3). Read-only.

    Stage 10: `q` (already length-capped at the boundary) filters by
    case-insensitive title/filename substring; blank searches behave as
    absent. The `document` pointer degrades to None when the linked row is
    absent OR its `file_type` is NULL (migration 0005 keeps NULL honest) —
    mirroring the detail, a present-but-unexpected type still 500s downstream.
    """
    query = q.strip() if q is not None else None
    if not query:
        query = None
    rows, total = await AnalysisRepository(session).list_owned(
        owner_id=owner_id,
        offset=(page - 1) * page_size,
        limit=page_size,
        sort=sort,
        band=band,
        source_type=source_type,
        q=query,
    )
    return (
        [
            AnalysisSummary(
                id=row.id,
                title=row.title,
                status=row.status,
                source_type=row.source_type,
                document=(
                    DocumentRef(filename=row.filename, file_type=row.file_type)
                    if row.filename is not None and row.file_type is not None
                    else None
                ),
                source_excerpt=row.source_excerpt,
                score=row.score,
                band=row.band,
                requirements_count=row.requirements_count,
                issues_count=row.issues_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total,
    )


@transactional
async def delete_analysis(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> None:
    """Delete one owned analysis (requirements + issues cascade). 404 unless
    owned — foreign ids are indistinguishable from missing ones. A linked
    document whose LAST referencing analysis this is goes too (row + storage
    object — no orphaned binaries); shared documents survive."""
    row = await AnalysisRepository(session).get_owned(owner_id=owner_id, analysis_id=analysis_id)
    if row is None:
        raise NotFoundError("analysis")
    document_id = row.document_id
    await AnalysisRepository(session).delete(row)
    if document_id is not None:
        await _delete_orphaned_document(session, owner_id=owner_id, document_id=document_id)
    logger.info(
        "analysis deleted analysis_id=%s owner_id=%s",
        analysis_id,
        owner_id,
        extra={"analysis_stage": "delete"},
    )


async def _delete_orphaned_document(
    session: AsyncSession, *, owner_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Remove a document row + binary iff no analysis references it anymore.
    Runs INSIDE the caller's transaction, rows first: a storage failure rolls
    the rows back (fully clean); only a commit failure after a storage delete
    could orphan a row (rare, logged, metadata-intact)."""
    remaining = await DocumentRepository(session).count_referencing_analyses(
        document_id=document_id
    )
    if remaining > 0:
        return
    doc = await DocumentRepository(session).get_owned(owner_id=owner_id, document_id=document_id)
    if doc is None:  # same-owner by construction — defensive only
        return
    await DocumentRepository(session).delete(doc)
    get_storage_backend().delete(doc.storage_path)
    logger.info(
        "orphaned document purged document_id=%s owner_id=%s",
        document_id,
        owner_id,
        extra={"document_stage": "orphan_purge", "storage_operation": "delete"},
    )


async def retry_analysis_ai(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
) -> AnalysisDetail:
    """Re-run ONLY the AI enhancement step of a persisted analysis (Stage 17).

    Reset → re-read → enhance: the reset clears the previous AI payload
    (overview/provider/error NULLs + AI-stamped rewrites dropped) in ONE short
    transaction so a failed retry can never strand stale `ok` output under a
    `failed` status; the re-read builds a rewrite-free detail for the shared
    step; `enhance_analysis` then runs exactly as on the creation path (same
    chain, caps, fail-open, persistence). No transaction spans provider I/O.
    Deterministic columns are never written here — scores/issues survive every
    outcome, including a mid-run concurrent DELETE (the outcome orphans by
    design, logged with ids only). 404 unless owned (no oracle).
    """
    detail = await get_analysis_detail(session, owner_id=owner_id, analysis_id=analysis_id)
    await _reset_ai_outcome(
        session, owner_id=owner_id, analysis_id=analysis_id, ai_status=detail.ai_status
    )
    fresh = await get_analysis_detail(session, owner_id=owner_id, analysis_id=analysis_id)
    # Lazy import: same cycle as `create_text_analysis` (ai_enhancement owns
    # AnalysisDetail from THIS module).
    from app.services.ai_enhancement import enhance_analysis

    return await enhance_analysis(session, owner_id=owner_id, detail=fresh, ai_enhance=True)


@transactional
async def _reset_ai_outcome(
    session: AsyncSession, *, owner_id: uuid.UUID, analysis_id: uuid.UUID, ai_status: str
) -> None:
    """Clear the previous AI payload ahead of a retry (short txn, no I/O).

    `ai_status` is deliberately left in place until the new outcome lands —
    the only observable intermediate is "old status, cleared payload", and
    only to a concurrent reader inside this request's window.
    """
    await AnalysisRepository(session).record_ai_result(
        owner_id=owner_id,
        analysis_id=analysis_id,
        ai_overview=None,
        ai_provider=None,
        ai_status=ai_status,
        ai_error=None,
    )
    await RequirementRepository(session).clear_ai_rewrites(analysis_id=analysis_id)
