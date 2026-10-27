"""Dashboard snapshot assembly (API_CONTRACT §4.5, Stage 11). Read-only.

Pure of HTTP: takes a session + owner + range, returns plain dataclasses (the
router maps them via `presenters.dashboard_response`). All inputs are
ownership-scoped aggregates — unscored (`failed`/legacy) runs count toward
totals and trend volume but NEVER toward averages, bands, improvements, or
risk; `latest` is the newest run overall even when it never scored.

Rules owned here (locked by tests + contract §4.5):
- Ranges: `30d` = 30 trailing UTC days ending today; `12w` = 12 trailing ISO
  weeks (Monday-start, UTC) ending this week. Buckets are `YYYY-MM-DD` (the
  day, or the week's Monday) and the window is ALWAYS zero-filled — sparse
  buckets would read as missing data.
- Averages round half-up to 1 decimal (score-scale convention: the analysis
  score itself rounds half-up, so its averages do too).
- `improved_count` = scored runs (oldest-first) scoring STRICTLY above the
  immediately preceding scored run. A neutral count, not a verdict.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.dashboard import DashboardRepository, TrendGranularity
from app.services import analysis as analysis_service
from app.services.analysis import AnalysisSummary

logger = get_logger(__name__)

DashboardRange = Literal["30d", "12w"]

BAND_ORDER = ("low", "moderate", "high", "very_high")
SEVERITY_ORDER = ("low", "medium", "high", "critical")
SOURCE_ORDER = ("text", "document")
RECENT_LIMIT = 5

_RANGE_GRANULARITY: dict[DashboardRange, TrendGranularity] = {
    "30d": "day",
    "12w": "week",
}


def _round_score(value: Decimal | float | int) -> float:
    """Score-scale average: half-up to 1 decimal (deterministic display)."""
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class DashboardLatest:
    id: uuid.UUID
    title: str
    score: int | None
    band: str | None
    created_at: datetime


@dataclass(frozen=True)
class DashboardTopCategory:
    category: str
    count: int


@dataclass(frozen=True)
class DashboardStats:
    analyses_total: int
    analyses_scored: int
    requirements_total: int
    issues_total: int
    avg_score: float | None
    latest: DashboardLatest | None
    high_risk_count: int
    improved_count: int
    top_category: DashboardTopCategory | None


@dataclass(frozen=True)
class DashboardBandCount:
    band: str
    count: int


@dataclass(frozen=True)
class DashboardSourceCount:
    source_type: str
    count: int


@dataclass(frozen=True)
class DashboardCategoryCount:
    category: str
    count: int


@dataclass(frozen=True)
class DashboardSeverityCount:
    severity: str
    count: int


@dataclass(frozen=True)
class DashboardTrendBucket:
    bucket: str
    avg_score: float | None
    analyses: int
    requirements: int


@dataclass(frozen=True)
class DashboardData:
    range: str
    stats: DashboardStats
    bands: tuple[DashboardBandCount, ...]
    sources: tuple[DashboardSourceCount, ...]
    categories: tuple[DashboardCategoryCount, ...]
    severity: tuple[DashboardSeverityCount, ...]
    trend: tuple[DashboardTrendBucket, ...]
    recent: tuple[AnalysisSummary, ...]


def _window_start(today: datetime, window: DashboardRange) -> datetime:
    """First bucket's UTC midnight: 29 days back (`30d`) or 11 Mondays back."""
    if window == "30d":
        first = today - timedelta(days=29)
        return datetime(first.year, first.month, first.day, tzinfo=UTC)
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=11)
    return datetime(first.year, first.month, first.day, tzinfo=UTC)


async def get_dashboard(
    session: AsyncSession, *, owner_id: uuid.UUID, window: DashboardRange
) -> DashboardData:
    """Assemble one deterministic dashboard snapshot. Read-only."""
    repository = DashboardRepository(session)
    today = datetime.now(UTC)
    start = _window_start(today, window)
    granularity = _RANGE_GRANULARITY[window]

    overview = await repository.overview(owner_id=owner_id)
    issues_total = await repository.issues_total(owner_id=owner_id)
    band_rows = await repository.band_counts(owner_id=owner_id)
    source_rows = await repository.source_counts(owner_id=owner_id)
    category_rows = await repository.category_counts(owner_id=owner_id)
    severity_rows = await repository.severity_counts(owner_id=owner_id)
    improved = await repository.improved_count(owner_id=owner_id)
    latest_row = await repository.latest(owner_id=owner_id)
    trend_rows = await repository.trend_rows(
        owner_id=owner_id, since=start, granularity=granularity
    )
    recent_rows, _ = await analysis_service.list_analyses(
        session,
        owner_id=owner_id,
        page=1,
        page_size=RECENT_LIMIT,
        sort="-created_at",
        band=None,
        source_type=None,
        q=None,
    )

    bands = {band: count for band, count in band_rows}
    sources = {source: count for source, count in source_rows}
    severities = {severity: count for severity, count in severity_rows}
    by_bucket = {row.bucket: row for row in trend_rows}

    step = timedelta(days=1 if granularity == "day" else 7)
    bucket_count = 30 if granularity == "day" else 12
    trend: list[DashboardTrendBucket] = []
    cursor = start.date()
    for _ in range(bucket_count):
        row = by_bucket.get(cursor)
        trend.append(
            DashboardTrendBucket(
                bucket=cursor.isoformat(),
                avg_score=(
                    _round_score(row.avg_score) if row and row.avg_score is not None else None
                ),
                analyses=row.analyses if row else 0,
                requirements=row.requirements if row else 0,
            )
        )
        cursor += step

    latest = (
        DashboardLatest(
            id=latest_row.id,
            title=latest_row.title,
            score=latest_row.score,
            band=latest_row.band,
            created_at=latest_row.created_at,
        )
        if latest_row is not None
        else None
    )
    top_category = (
        DashboardTopCategory(category=category_rows[0][0], count=category_rows[0][1])
        if category_rows
        else None
    )

    logger.info(
        "dashboard snapshot owner_id=%s range=%s analyses=%d issues=%d",
        owner_id,
        window,
        overview.analyses_total,
        issues_total,
    )
    return DashboardData(
        range=window,
        stats=DashboardStats(
            analyses_total=overview.analyses_total,
            analyses_scored=overview.analyses_scored,
            requirements_total=overview.requirements_total,
            issues_total=issues_total,
            avg_score=_round_score(overview.avg_score) if overview.avg_score is not None else None,
            latest=latest,
            high_risk_count=overview.high_risk_count,
            improved_count=improved,
            top_category=top_category,
        ),
        bands=tuple(DashboardBandCount(band=band, count=bands.get(band, 0)) for band in BAND_ORDER),
        sources=tuple(
            DashboardSourceCount(source_type=source, count=sources.get(source, 0))
            for source in SOURCE_ORDER
        ),
        categories=tuple(
            DashboardCategoryCount(category=category, count=count)
            for category, count in category_rows
        ),
        severity=tuple(
            DashboardSeverityCount(severity=severity, count=severities.get(severity, 0))
            for severity in SEVERITY_ORDER
        ),
        trend=tuple(trend),
        recent=tuple(recent_rows),
    )
