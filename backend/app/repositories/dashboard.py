"""Dashboard rollups (API_CONTRACT §4.5, Stage 11). Pure SQLAlchemy aggregates —
no rules, no window math, no rounding here: the caller passes `owner_id` (never
a client id) plus explicit bounds, and gets back plain rows the service shapes
into the contracted snapshot. Every query is ownership-scoped and served by
the dashboard indexes (`(owner_id, created_at)`, `(analysis_id, severity/
category)`); nothing here loads per-row history into Python.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.issue import Issue


@dataclass(frozen=True)
class DashboardLatestRow:
    """Newest owned analysis projected for dashboard stats only.

    Avoids loading large `source_text`/AI/detail JSON columns for a title +
    score card.
    """

    id: uuid.UUID
    title: str
    score: int | None
    band: str | None
    created_at: datetime


TrendGranularity = Literal["day", "week"]


@dataclass(frozen=True)
class DashboardOverview:
    """Account totals in ONE query. `avg_score` covers scored analyses only
    (None when the account holds none); `requirements_total` sums the
    denormalized per-analysis counts (DATABASE_SCHEMA §3.2: kept for
    dashboard speed)."""

    analyses_total: int
    analyses_scored: int
    avg_score: Decimal | None
    requirements_total: int
    high_risk_count: int


@dataclass(frozen=True)
class TrendRow:
    """One non-empty UTC bucket: `bucket` is the calendar day (`day`) or the
    week's Monday (`week`). `avg_score` is None when the bucket holds no
    scored analysis; `analyses` counts every run in the bucket."""

    bucket: date
    avg_score: Decimal | None
    analyses: int
    requirements: int


class DashboardRepository:
    """Ownership-scoped aggregate reads for the dashboard snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(self, *, owner_id: uuid.UUID) -> DashboardOverview:
        row = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count(Analysis.score),
                    func.avg(Analysis.score),
                    func.coalesce(func.sum(Analysis.requirements_count), 0),
                    func.count().filter(Analysis.band.in_(["high", "very_high"])),
                ).where(Analysis.owner_id == owner_id)
            )
        ).one()
        return DashboardOverview(
            analyses_total=row[0],
            analyses_scored=row[1],
            avg_score=row[2],
            requirements_total=row[3],
            high_risk_count=row[4],
        )

    async def issues_total(self, *, owner_id: uuid.UUID) -> int:
        return (
            await self._session.execute(
                select(func.count()).select_from(Issue).where(Issue.owner_id == owner_id)
            )
        ).scalar_one()

    async def band_counts(self, *, owner_id: uuid.UUID) -> list[tuple[str, int]]:
        """(band, count) for bands present — the service zero-fills all four."""
        result = await self._session.execute(
            select(Analysis.band, func.count())
            .where(Analysis.owner_id == owner_id, Analysis.band.is_not(None))
            .group_by(Analysis.band)
        )
        return [(band, count) for band, count in result.all() if band is not None]

    async def source_counts(self, *, owner_id: uuid.UUID) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(Analysis.source_type, func.count())
            .where(Analysis.owner_id == owner_id)
            .group_by(Analysis.source_type)
        )
        return [(first, second) for first, second in result.all()]

    async def category_counts(self, *, owner_id: uuid.UUID) -> list[tuple[str, int]]:
        """(category, count), most-frequent first (category asc breaks ties —
        deterministic; the fixed 11-detector vocabulary needs no top-N cut)."""
        result = await self._session.execute(
            select(Issue.category, func.count())
            .where(Issue.owner_id == owner_id)
            .group_by(Issue.category)
            .order_by(func.count().desc(), Issue.category.asc())
        )
        return [(first, second) for first, second in result.all()]

    async def severity_counts(self, *, owner_id: uuid.UUID) -> list[tuple[str, int]]:
        """(severity, count) for severities present — service zero-fills."""
        result = await self._session.execute(
            select(Issue.severity, func.count())
            .where(Issue.owner_id == owner_id)
            .group_by(Issue.severity)
        )
        return [(first, second) for first, second in result.all()]

    async def improved_count(self, *, owner_id: uuid.UUID) -> int:
        """Count scored runs whose score strictly improved over the previous
        scored run, without loading every score into Python.
        """
        scored = (
            select(
                Analysis.score.label("score"),
                func.lag(Analysis.score)
                .over(order_by=(Analysis.created_at.asc(), Analysis.id.asc()))
                .label("previous_score"),
            )
            .where(Analysis.owner_id == owner_id, Analysis.score.is_not(None))
            .subquery()
        )
        return (
            await self._session.execute(
                select(func.count())
                .select_from(scored)
                .where(scored.c.score > scored.c.previous_score)
            )
        ).scalar_one()

    async def latest(self, *, owner_id: uuid.UUID) -> DashboardLatestRow | None:
        """Newest owned run overall (scored or not — `created_at, id`)."""
        result = await self._session.execute(
            select(Analysis.id, Analysis.title, Analysis.score, Analysis.band, Analysis.created_at)
            .where(Analysis.owner_id == owner_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return DashboardLatestRow(
            id=row[0], title=row[1], score=row[2], band=row[3], created_at=row[4]
        )

    async def trend_rows(
        self, *, owner_id: uuid.UUID, since: datetime, granularity: TrendGranularity
    ) -> list[TrendRow]:
        """Non-empty UTC buckets at/after `since` (`date_trunc` day/week —
        weeks start Monday per PostgreSQL semantics). The service zero-fills
        the trailing window around these rows."""
        bucket = func.date_trunc(granularity, Analysis.created_at).cast(Date)
        result = await self._session.execute(
            select(
                bucket,
                func.avg(Analysis.score),
                func.count(),
                func.coalesce(func.sum(Analysis.requirements_count), 0),
            )
            .where(Analysis.owner_id == owner_id, Analysis.created_at >= since)
            .group_by(bucket)
            .order_by(bucket.asc())
        )
        return [
            TrendRow(bucket=row[0], avg_score=row[1], analyses=row[2], requirements=row[3])
            for row in result.all()
        ]
