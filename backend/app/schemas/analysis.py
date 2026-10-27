"""Analysis API boundary models (API_CONTRACT §4.3 — Stage 08 subset).

TEXT posts here; FILE uploads go to POST /documents/upload (which reuses the
same pipeline and returns this same detail shape with `source_type` set
accordingly and `document` populated). `document_id` stays
accepted-but-rejected (400 — re-analyzing a stored document BY ID has no
pipeline yet); `options.ai_enhance` is LIVE since Stage 14 (false =
deterministic-only `skipped`; true = deterministic + optional AI with an
honest `ai_status`). POST scores every requirement with the deterministic
engine (`analyzed`); pre-Stage-07 `segmented` rows still read back with
NULL scores.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TITLE_MAX_LENGTH = 200  # mirrors analyses.title VARCHAR(200)
TEXT_MAX_LENGTH = 200_000  # contract §4.3: chars, enforced by the schema (400)


class AnalysisOptions(BaseModel):
    ai_enhance: bool = False


class AnalysisCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_MAX_LENGTH)
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    document_id: uuid.UUID | None = None
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None  # blank → service fallback title

    @field_validator("text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        # Whitespace-only input is a FIELD error (400 validation_error with a
        # `text` loc the UI maps to the editor) — not an attempted analysis.
        # The service still owns normalization; this only classifies blankness.
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class SegmentationMetaResponse(BaseModel):
    """How one requirement was segmented (evidence for the Stage 07 engine)."""

    strategy: str
    confidence: float
    start_offset: int
    end_offset: int
    line_start: int
    line_end: int


class IssueResponse(BaseModel):
    """One detector finding (contract §4.3 issue shape, exactly: no
    `requirement_id` — the nesting already says which requirement owns it)."""

    id: uuid.UUID
    detector_id: str
    category: str
    severity: str
    phrase: str
    start_offset: int
    end_offset: int
    reason: str
    recommendation: str
    ai_explanation: str | None = None


class RequirementResponse(BaseModel):
    """One scored requirement: `score` 0–100, `severity` = highest issue
    severity (None when clean), `suggested_rewrite` None until the AI
    enhancement stamps one (`suggestion_source='ai'`; `'rule'` reserved)."""

    id: uuid.UUID
    position: int
    identifier: str | None
    section: str | None = None
    text: str
    score: int | None = None
    severity: str | None = None
    issues_count: int = 0
    suggested_rewrite: str | None = None
    suggestion_source: str | None = None
    segmentation: SegmentationMetaResponse
    issues: list[IssueResponse] = Field(default_factory=list)


class DocumentRefResponse(BaseModel):
    """Source-document pointer for `source_type == "document"` (Stage 09):
    display metadata ONLY — filename + validated type. No document id (the
    UI needs no document link yet), no storage key, no binary, ever."""

    filename: str
    file_type: Literal["pdf", "docx", "txt"]


class AnalysisDetailResponse(BaseModel):
    """Analysis detail (contract §4.3, Stage 07 amendment: `status` is
    `analyzed` for engine-scored rows (`segmented` only for pre-Stage-07
    rows); `score`/`band`/`score_breakdown`/`health` populated by the
    engine; issues nested per requirement; no top-level `issues`, no
    `source_excerpt` (summary-only)."""

    id: uuid.UUID
    title: str
    status: Literal["segmented", "analyzed", "failed"]
    source_type: Literal["text", "document"]
    document: DocumentRefResponse | None = None
    score: int | None = None
    band: str | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    requirements_count: int
    issues_count: int
    health: dict[str, Any] | None = None
    ai_overview: str | None = None
    ai_provider: str | None = None
    ai_status: Literal["ok", "failed", "skipped", "unconfigured"] = "skipped"
    ai_error: str | None = None
    requirements: list[RequirementResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RetryAiResponse(BaseModel):
    """POST /analysis/{id}/retry-ai (Stage 17): the AI outcome subset only.

    The deterministic record is untouched by a retry, so the response carries
    just the four restamped fields; clients re-read the full detail (fresh
    rewrites included) the same way they do after any mutation.
    """

    ai_status: Literal["ok", "failed", "skipped", "unconfigured"]
    ai_overview: str | None
    ai_provider: str | None
    ai_error: str | None


class AnalysisSummaryResponse(BaseModel):
    """History-list row: detail minus `requirements`, plus `source_excerpt`.
    Stage 10: carries the `document` display pointer (like the detail)."""

    id: uuid.UUID
    title: str
    status: Literal["segmented", "analyzed", "failed"]
    source_type: Literal["text", "document"]
    document: DocumentRefResponse | None = None
    source_excerpt: str | None = None
    score: int | None = None
    band: str | None = None
    requirements_count: int
    issues_count: int
    created_at: datetime
    updated_at: datetime
