"""Privacy/data-lifecycle schemas (API_CONTRACT §4.7, Stage 23)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

RetentionDays = int | None


class PrivacySettingsResponse(BaseModel):
    """GET/PATCH /settings/privacy — enforced lifecycle preferences."""

    history_retention_days: RetentionDays = Field(default=None, ge=1, le=3650)


class PrivacySettingsUpdateRequest(BaseModel):
    """PATCH /settings/privacy — explicit null disables automatic retention."""

    history_retention_days: RetentionDays = Field(default=None, ge=1, le=3650)


class PrivacyExportTicketResponse(BaseModel):
    """POST /privacy/export — signed, expiring export ticket."""

    export_id: str
    download_url: str
    expires_at: dt.datetime


class PrivacyPurgeRequest(BaseModel):
    """POST /privacy/purge-history.

    `older_than_days` is optional in the API contract; when omitted the backend
    uses the caller's configured `history_retention_days`. If neither exists,
    the service raises `validation_error` rather than purging unexpectedly.
    """

    older_than_days: int | None = Field(default=None, ge=1, le=3650)


class PrivacyPurgeResponse(BaseModel):
    deleted_analyses: int
    deleted_documents: int


class ExportProfile(BaseModel):
    email: str
    display_name: str | None
    is_verified: bool
    is_active: bool
    created_at: dt.datetime


class ExportIssue(BaseModel):
    id: uuid.UUID
    detector_id: str
    category: str
    severity: str
    phrase: str
    start_offset: int
    end_offset: int
    reason: str
    recommendation: str
    ai_explanation: str | None
    created_at: dt.datetime


class ExportRequirement(BaseModel):
    id: uuid.UUID
    position: int
    identifier: str | None
    section: str | None
    text: str
    score: int | None
    severity: str | None
    issues_count: int
    suggested_rewrite: str | None
    suggestion_source: str | None
    segmentation: dict[str, object] | None
    created_at: dt.datetime
    issues: list[ExportIssue]


class ExportDocumentRef(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: Literal["pdf", "docx", "txt"] | None
    mime_type: str
    byte_size: int
    sha256: str
    extracted_chars: int | None
    extraction_status: str
    created_at: dt.datetime


class ExportAnalysis(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    source_excerpt: str | None
    status: str
    source_text: str | None
    score: int | None
    band: str | None
    score_breakdown: dict[str, object]
    requirements_count: int
    issues_count: int
    health: dict[str, object] | None
    ai_overview: str | None
    ai_provider: str | None
    ai_status: str
    ai_error: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    document: ExportDocumentRef | None
    requirements: list[ExportRequirement]


class ExportDocument(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: Literal["pdf", "docx", "txt"] | None
    mime_type: str
    byte_size: int
    sha256: str
    extracted_chars: int | None
    extraction_status: str
    created_at: dt.datetime


class ExportAICredentialMetadata(BaseModel):
    id: uuid.UUID
    provider: str
    label: str | None
    is_enabled: bool
    is_default: bool
    fallback_rank: int
    key_version: int
    last_tested_at: dt.datetime | None
    last_test_status: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class PrivacyExportResponse(BaseModel):
    """Allowlist export. No hashes, tokens, storage paths, ciphertext, or keys."""

    exported_at: dt.datetime
    profile: ExportProfile
    privacy_settings: PrivacySettingsResponse
    analyses: list[ExportAnalysis]
    documents: list[ExportDocument]
    ai_provider_credentials: list[ExportAICredentialMetadata]
