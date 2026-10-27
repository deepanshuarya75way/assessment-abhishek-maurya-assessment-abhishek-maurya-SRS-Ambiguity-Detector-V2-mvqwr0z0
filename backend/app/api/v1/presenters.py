"""Service dataclasses → response schemas (ONE mapping, every router).

Stage 08 added a second producer of analysis details (document upload) — these
mappers moved here from `endpoints/analysis.py` so TEXT and DOCUMENT responses
are byte-identical by construction, not by parallel maintenance. Pydantic
re-validates every value on the way out: service/DB drift 500s, never lies.
"""

from app.models.ai_credential import AICredential
from app.schemas.ai_providers import ProviderMetadataResponse
from app.schemas.analysis import (
    AnalysisDetailResponse,
    AnalysisSummaryResponse,
    DocumentRefResponse,
    IssueResponse,
    RequirementResponse,
    RetryAiResponse,
    SegmentationMetaResponse,
)
from app.schemas.dashboard import (
    DashboardBandCount,
    DashboardCategoryCount,
    DashboardLatestResponse,
    DashboardResponse,
    DashboardSeverityCount,
    DashboardSourceCount,
    DashboardStatsResponse,
    DashboardTopCategoryResponse,
    DashboardTrendBucket,
)
from app.services.analysis import (
    AnalysisDetail,
    AnalysisSummary,
    DocumentRef,
    IssueDetail,
    RequirementDetail,
)
from app.services.dashboard import DashboardData

_VALID_STATUSES = ("segmented", "analyzed", "failed")
_VALID_SOURCE_TYPES = ("text", "document")
_VALID_AI_STATUSES = ("ok", "failed", "skipped", "unconfigured")


def _document_response(doc: DocumentRef | None) -> DocumentRefResponse | None:
    """Shared detail/summary pointer mapping (Stage 10): absent degrades to
    None upstream; a present-but-unexpected type 500s (drift never lies)."""
    if doc is None:
        return None
    if doc.file_type not in ("pdf", "docx", "txt"):
        raise ValueError(f"unexpected file type: {doc.file_type!r}")
    return DocumentRefResponse(
        filename=doc.filename,
        file_type=doc.file_type,  # type: ignore[arg-type]  # narrowed above
    )


def issue_response(item: IssueDetail) -> IssueResponse:
    return IssueResponse(
        id=item.id,
        detector_id=item.detector_id,
        category=item.category,
        severity=item.severity,
        phrase=item.phrase,
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        reason=item.reason,
        recommendation=item.recommendation,
        ai_explanation=item.ai_explanation,
    )


def requirement_response(item: RequirementDetail) -> RequirementResponse:
    # `segmentation` is service-built (fixed keys, JSON-safe values).
    meta = item.segmentation
    return RequirementResponse(
        id=item.id,
        position=item.position,
        identifier=item.identifier,
        section=item.section,
        text=item.text,
        score=item.score,
        severity=item.severity,
        issues_count=item.issues_count,
        suggested_rewrite=item.suggested_rewrite,
        suggestion_source=item.suggestion_source,
        segmentation=SegmentationMetaResponse(
            strategy=meta["strategy"],
            confidence=meta["confidence"],
            start_offset=meta["start_offset"],
            end_offset=meta["end_offset"],
            line_start=meta["line_start"],
            line_end=meta["line_end"],
        ),
        issues=[issue_response(issue) for issue in item.issues],
    )


def detail_response(detail: AnalysisDetail) -> AnalysisDetailResponse:
    if detail.status not in _VALID_STATUSES:
        raise ValueError(f"unexpected analysis status: {detail.status!r}")
    if detail.source_type not in _VALID_SOURCE_TYPES:
        raise ValueError(f"unexpected source type: {detail.source_type!r}")
    if detail.ai_status not in _VALID_AI_STATUSES:
        raise ValueError(f"unexpected AI status: {detail.ai_status!r}")
    document = _document_response(detail.document)
    return AnalysisDetailResponse(
        id=detail.id,
        title=detail.title,
        document=document,
        status=detail.status,  # type: ignore[arg-type]  # narrowed above
        source_type=detail.source_type,  # type: ignore[arg-type]  # narrowed above
        score=detail.score,
        band=detail.band,
        score_breakdown=detail.score_breakdown,
        requirements_count=detail.requirements_count,
        issues_count=detail.issues_count,
        health=detail.health,
        ai_overview=detail.ai_overview,
        ai_provider=detail.ai_provider,
        ai_status=detail.ai_status,  # type: ignore[arg-type]  # narrowed above
        ai_error=detail.ai_error,
        requirements=[requirement_response(item) for item in detail.requirements],
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )


def retry_ai_response(detail: AnalysisDetail) -> RetryAiResponse:
    """The four restamped AI fields after a retry (Stage 17 — deterministic
    columns are untouched by retries, so they stay out of the response)."""
    if detail.ai_status not in _VALID_AI_STATUSES:
        raise ValueError(f"unexpected AI status: {detail.ai_status!r}")
    return RetryAiResponse(
        ai_status=detail.ai_status,  # type: ignore[arg-type]  # narrowed above
        ai_overview=detail.ai_overview,
        ai_provider=detail.ai_provider,
        ai_error=detail.ai_error,
    )


def summary_response(item: AnalysisSummary) -> AnalysisSummaryResponse:
    if item.status not in _VALID_STATUSES:
        raise ValueError(f"unexpected analysis status: {item.status!r}")
    if item.source_type not in _VALID_SOURCE_TYPES:
        raise ValueError(f"unexpected source type: {item.source_type!r}")
    return AnalysisSummaryResponse(
        id=item.id,
        title=item.title,
        status=item.status,  # type: ignore[arg-type]  # narrowed above
        source_type=item.source_type,  # type: ignore[arg-type]  # narrowed above
        document=_document_response(item.document),
        source_excerpt=item.source_excerpt,
        score=item.score,
        band=item.band,
        requirements_count=item.requirements_count,
        issues_count=item.issues_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def dashboard_response(data: DashboardData) -> DashboardResponse:
    """Dashboard snapshot → response (Stage 11). Pydantic re-validates the
    fixed vocabularies (bands/severities/sources) on the way out."""
    stats = data.stats
    return DashboardResponse(
        range=data.range,  # type: ignore[arg-type]  # Literal["30d", "12w"] by construction
        stats=DashboardStatsResponse(
            analyses_total=stats.analyses_total,
            analyses_scored=stats.analyses_scored,
            requirements_total=stats.requirements_total,
            issues_total=stats.issues_total,
            avg_score=stats.avg_score,
            latest=(
                DashboardLatestResponse(
                    id=stats.latest.id,
                    title=stats.latest.title,
                    score=stats.latest.score,
                    band=stats.latest.band,
                    created_at=stats.latest.created_at,
                )
                if stats.latest is not None
                else None
            ),
            high_risk_count=stats.high_risk_count,
            improved_count=stats.improved_count,
            top_category=(
                DashboardTopCategoryResponse(
                    category=stats.top_category.category,
                    count=stats.top_category.count,
                )
                if stats.top_category is not None
                else None
            ),
        ),
        bands=[
            DashboardBandCount(band=item.band, count=item.count)  # type: ignore[arg-type]  # fixed order
            for item in data.bands
        ],
        sources=[
            DashboardSourceCount(source_type=item.source_type, count=item.count)  # type: ignore[arg-type]
            for item in data.sources
        ],
        categories=[
            DashboardCategoryCount(category=item.category, count=item.count)
            for item in data.categories
        ],
        severity=[
            DashboardSeverityCount(severity=item.severity, count=item.count)  # type: ignore[arg-type]  # fixed order
            for item in data.severity
        ],
        trend=[
            DashboardTrendBucket(
                bucket=item.bucket,
                avg_score=item.avg_score,
                analyses=item.analyses,
                requirements=item.requirements,
            )
            for item in data.trend
        ],
        recent=[summary_response(item) for item in data.recent],
    )


def provider_response(row: AICredential) -> ProviderMetadataResponse:
    """Vault row → safe metadata: `masked_key` is 12 bullets + last4 — the
    ONLY key-derived value that ever leaves the server. A provider id outside
    the registry (schema drift / tampered row) 500s (drift never lies)."""
    if row.provider not in (
        "gemini",
        "groq",
        "openai",
        "anthropic",
        "openrouter",
        "huggingface",
    ):
        raise ValueError(f"unexpected provider: {row.provider!r}")
    return ProviderMetadataResponse(
        id=row.id,
        provider=row.provider,  # type: ignore[arg-type]  # narrowed above
        label=row.label,
        masked_key=f"{'•' * 12}{row.last4}",
        is_enabled=row.is_enabled,
        is_default=row.is_default,
        fallback_rank=row.fallback_rank,
        key_version=row.key_version,
        last_tested_at=row.last_tested_at,
        last_test_status=row.last_test_status,  # type: ignore[arg-type]  # ck-guarded
    )
