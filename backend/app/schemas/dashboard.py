"""Dashboard aggregates (API_CONTRACT §4.5 — Stage 11: ONE aggregate response).

The contract's planned five endpoints collapsed into a single `GET /dashboard`
(Stage 11 amendment): one round trip, one deterministic snapshot, no N+1. The
metric vocabulary is unchanged — totals, average score, band/source/category/
severity distributions, UTC-bucketed trend + activity, recent summaries.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.analysis import AnalysisSummaryResponse

DashboardRange = Literal["30d", "12w"]


class DashboardLatestResponse(BaseModel):
    """Newest owned analysis (score/band null when the run never scored)."""

    id: UUID
    title: str
    score: int | None = None
    band: str | None = None
    created_at: datetime


class DashboardTopCategoryResponse(BaseModel):
    """Most frequent owned issue category (null when no issues exist)."""

    category: str
    count: int


class DashboardStatsResponse(BaseModel):
    """Account totals. Averages cover SCORED analyses only (`avg_score` null
    when none); `latest` is the newest run overall (score may be null)."""

    analyses_total: int
    analyses_scored: int
    requirements_total: int
    issues_total: int
    avg_score: float | None = None
    latest: DashboardLatestResponse | None = None
    high_risk_count: int
    improved_count: int
    top_category: DashboardTopCategoryResponse | None = None


class DashboardBandCount(BaseModel):
    """Scored analyses per persisted band — always all four bands."""

    band: Literal["low", "moderate", "high", "very_high"]
    count: int


class DashboardSourceCount(BaseModel):
    """Owned analyses per source type — always both rows."""

    source_type: Literal["text", "document"]
    count: int


class DashboardCategoryCount(BaseModel):
    """Owned issues per detector category — non-zero only, count desc."""

    category: str
    count: int


class DashboardSeverityCount(BaseModel):
    """Owned issues per severity — always all four severities."""

    severity: Literal["low", "medium", "high", "critical"]
    count: int


class DashboardTrendBucket(BaseModel):
    """One UTC bucket of the trailing window (zero-filled, never sparse).

    `bucket` is a calendar date (`YYYY-MM-DD`): the UTC day for `30d`, the
    week's Monday (UTC) for `12w`. `avg_score` averages SCORED analyses in
    the bucket (null when the bucket holds none — never a fake zero) while
    `analyses` counts every run in the bucket, scored or not.
    """

    bucket: str
    avg_score: float | None = None
    analyses: int
    requirements: int


class DashboardResponse(BaseModel):
    """Full dashboard snapshot for the authenticated user (never 404:
    empty accounts get zeros + empty arrays + nulls + a zero-filled trend)."""

    range: DashboardRange
    stats: DashboardStatsResponse
    bands: list[DashboardBandCount]
    sources: list[DashboardSourceCount]
    categories: list[DashboardCategoryCount]
    severity: list[DashboardSeverityCount]
    trend: list[DashboardTrendBucket]
    recent: list[AnalysisSummaryResponse]
