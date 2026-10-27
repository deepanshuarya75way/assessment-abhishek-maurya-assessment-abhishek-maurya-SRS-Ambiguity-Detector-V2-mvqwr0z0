"""Privacy/data lifecycle service (Stage 23).

This module owns the non-transactional boundary between database rows and object
storage. PostgreSQL cannot include storage operations in its transaction, so the
chosen strategy is:

1. Select owned storage keys from trusted DB rows.
2. Delete known storage objects through the storage abstraction first (missing is
   a no-op by the port contract; real backend failures abort the request).
3. Delete/commit DB rows only after storage deletion has not failed.

This prevents a successful API response from knowingly leaving user-owned
storage behind. A DB commit failure after storage deletion can still leave live
rows pointing at missing objects; that is a rare infrastructure failure and is
logged/handled by existing download integrity checks, not represented as
all-or-nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import utcnow
from app.exceptions import InternalError, UnauthorizedError, ValidationError
from app.models.document import Document
from app.repositories.auth import UserRepository
from app.repositories.privacy import DocumentStorageRef, PrivacyRepository
from app.schemas.privacy import (
    ExportAICredentialMetadata,
    ExportAnalysis,
    ExportDocument,
    ExportDocumentRef,
    ExportIssue,
    ExportProfile,
    ExportRequirement,
    PrivacyExportResponse,
    PrivacyPurgeResponse,
    PrivacySettingsResponse,
)
from app.services.transactions import transactional
from app.storage import get_storage_backend

logger = get_logger(__name__)


def _settings_response(history_retention_days: int | None) -> PrivacySettingsResponse:
    return PrivacySettingsResponse(history_retention_days=history_retention_days)


async def get_privacy_settings(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> PrivacySettingsResponse:
    row = await PrivacyRepository(session).get_preferences(owner_id=owner_id)
    return _settings_response(row.history_retention_days if row else None)


@transactional
async def update_privacy_settings(
    session: AsyncSession, *, owner_id: uuid.UUID, history_retention_days: int | None
) -> PrivacySettingsResponse:
    row = await PrivacyRepository(session).upsert_preferences(
        owner_id=owner_id, history_retention_days=history_retention_days
    )
    logger.info(
        "privacy settings updated owner_id=%s history_retention_days=%s",
        owner_id,
        history_retention_days,
    )
    return _settings_response(row.history_retention_days)


def _delete_storage_refs(refs: list[DocumentStorageRef]) -> None:
    backend = get_storage_backend()
    for ref in refs:
        try:
            backend.delete(ref.storage_path)
        except Exception:
            logger.error(
                "storage cleanup failed document_id=%s",
                ref.id,
                extra={"storage_operation": "delete", "error_code": "storage_cleanup_failed"},
            )
            raise InternalError("Data cleanup failed. Please try again.") from None


@transactional
async def purge_history(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    older_than_days: int | None,
    now: datetime | None = None,
) -> PrivacyPurgeResponse:
    repo = PrivacyRepository(session)
    retention_days = older_than_days
    if retention_days is None:
        settings = await repo.get_preferences(owner_id=owner_id)
        retention_days = settings.history_retention_days if settings else None
    if retention_days is None:
        raise ValidationError("Set a retention window or provide older_than_days.")
    cutoff = (now or utcnow()) - timedelta(days=retention_days)
    analyses = await repo.list_analyses_before(owner_id=owner_id, cutoff=cutoff)
    analysis_ids = {row.id for row in analyses}
    doc_refs = await repo.document_refs_purgeable_with_analyses(
        owner_id=owner_id, analysis_ids=analysis_ids
    )
    _delete_storage_refs(doc_refs)
    deleted_docs = await repo.delete_documents_by_ids(
        owner_id=owner_id, document_ids={ref.id for ref in doc_refs}
    )
    deleted_analyses = await repo.delete_analyses_by_ids(
        owner_id=owner_id, analysis_ids=analysis_ids
    )
    logger.info(
        "privacy history purged owner_id=%s older_than_days=%s analyses=%d documents=%d",
        owner_id,
        retention_days,
        deleted_analyses,
        deleted_docs,
    )
    return PrivacyPurgeResponse(deleted_analyses=deleted_analyses, deleted_documents=deleted_docs)


@dataclass(frozen=True)
class RetentionRunResult:
    users_scanned: int
    deleted_analyses: int
    deleted_documents: int


async def enforce_configured_retention(
    session: AsyncSession, *, now: datetime | None = None
) -> RetentionRunResult:
    """Maintenance seam for scheduled/CLI retention enforcement.

    No scheduler is claimed here. Operators can run `python -m app.cli.purge_retention`;
    future deployment stages can wire that command to cron/platform jobs.
    """
    prefs = await PrivacyRepository(session).list_users_with_retention()
    deleted_analyses = 0
    deleted_documents = 0
    for pref in prefs:
        result = await purge_history(
            session,
            owner_id=pref.owner_id,
            older_than_days=pref.history_retention_days,
            now=now,
        )
        deleted_analyses += result.deleted_analyses
        deleted_documents += result.deleted_documents
    return RetentionRunResult(
        users_scanned=len(prefs),
        deleted_analyses=deleted_analyses,
        deleted_documents=deleted_documents,
    )


async def purge_account_storage(session: AsyncSession, *, owner_id: uuid.UUID) -> None:
    """Delete every owned storage object before account row deletion.

    Used by `DELETE /auth/account`; storage paths are selected by owner from
    trusted metadata rows, never from client input.
    """
    refs = await PrivacyRepository(session).list_owned_storage_refs(owner_id=owner_id)
    _delete_storage_refs(refs)
    if refs:
        logger.info("account storage purged owner_id=%s documents=%d", owner_id, len(refs))


@transactional
async def delete_account_with_lifecycle(session: AsyncSession, *, user_id: uuid.UUID) -> str:
    """Purge storage objects, then hard-delete the user row (FK cascades DB data).

    Returns the captured email for the farewell notice; callers never inspect
    the deleted ORM row after commit.
    """
    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None:
        raise UnauthorizedError()
    email = user.email
    await purge_account_storage(session, owner_id=user.id)
    await users.delete(user)
    logger.info("account deleted user_id=%s", user_id)
    return email


def _export_file_type(value: str | None) -> Literal["pdf", "docx", "txt"] | None:
    if value in ("pdf", "docx", "txt"):
        return cast(Literal["pdf", "docx", "txt"], value)
    return None


def _document_ref(doc: Document) -> ExportDocumentRef:
    return ExportDocumentRef(
        id=doc.id,
        filename=doc.filename,
        file_type=_export_file_type(doc.file_type),
        mime_type=doc.mime_type,
        byte_size=doc.byte_size,
        sha256=doc.sha256,
        extracted_chars=doc.extracted_chars,
        extraction_status=doc.extraction_status,
        created_at=doc.created_at,
    )


def _export_document(doc: Document) -> ExportDocument:
    return ExportDocument(**_document_ref(doc).model_dump())


async def build_privacy_export(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> PrivacyExportResponse:
    repo = PrivacyRepository(session)
    user = await repo.load_export_user(owner_id=owner_id)
    if user is None or not user.is_active:
        raise UnauthorizedError()
    preferences = await repo.get_preferences(owner_id=owner_id)
    analyses = await repo.load_export_analyses(owner_id=owner_id)
    documents = await repo.load_export_documents(owner_id=owner_id)
    credentials = await repo.load_export_credentials(owner_id=owner_id)

    exported_analyses: list[ExportAnalysis] = []
    for analysis in analyses:
        requirements = []
        for requirement in sorted(analysis.requirements, key=lambda item: (item.position, item.id)):
            issues = [
                ExportIssue(
                    id=issue.id,
                    detector_id=issue.detector_id,
                    category=issue.category,
                    severity=issue.severity,
                    phrase=issue.phrase,
                    start_offset=issue.start_offset,
                    end_offset=issue.end_offset,
                    reason=issue.reason,
                    recommendation=issue.recommendation,
                    ai_explanation=issue.ai_explanation,
                    created_at=issue.created_at,
                )
                for issue in sorted(
                    requirement.issues, key=lambda item: (item.start_offset, item.id)
                )
            ]
            requirements.append(
                ExportRequirement(
                    id=requirement.id,
                    position=requirement.position,
                    identifier=requirement.identifier,
                    section=requirement.section,
                    text=requirement.text,
                    score=requirement.score,
                    severity=requirement.severity,
                    issues_count=requirement.issues_count,
                    suggested_rewrite=requirement.suggested_rewrite,
                    suggestion_source=requirement.suggestion_source,
                    segmentation=requirement.segmentation,
                    created_at=requirement.created_at,
                    issues=issues,
                )
            )
        exported_analyses.append(
            ExportAnalysis(
                id=analysis.id,
                title=analysis.title,
                source_type=analysis.source_type,
                source_excerpt=analysis.source_excerpt,
                status=analysis.status,
                source_text=analysis.source_text,
                score=analysis.score,
                band=analysis.band,
                score_breakdown=analysis.score_breakdown,
                requirements_count=analysis.requirements_count,
                issues_count=analysis.issues_count,
                health=analysis.health,
                ai_overview=analysis.ai_overview,
                ai_provider=analysis.ai_provider,
                ai_status=analysis.ai_status,
                ai_error=analysis.ai_error,
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
                document=(
                    _document_ref(analysis.document) if analysis.document is not None else None
                ),
                requirements=requirements,
            )
        )

    return PrivacyExportResponse(
        exported_at=utcnow(),
        profile=ExportProfile(
            email=user.email,
            display_name=user.display_name,
            is_verified=user.is_verified,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
        privacy_settings=_settings_response(
            preferences.history_retention_days if preferences else None
        ),
        analyses=exported_analyses,
        documents=[_export_document(row) for row in documents],
        ai_provider_credentials=[
            ExportAICredentialMetadata(
                id=row.id,
                provider=row.provider,
                label=row.label,
                is_enabled=row.is_enabled,
                is_default=row.is_default,
                fallback_rank=row.fallback_rank,
                key_version=row.key_version,
                last_tested_at=row.last_tested_at,
                last_test_status=row.last_test_status,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in credentials
        ],
    )
