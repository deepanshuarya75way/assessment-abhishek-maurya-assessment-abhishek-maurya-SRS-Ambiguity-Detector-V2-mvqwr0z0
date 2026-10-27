"""Privacy/data lifecycle persistence (Stage 23).

Owner scoping is applied in every query. Storage paths come only from trusted
`documents` rows; callers never supply deletion keys.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_credential import AICredential
from app.models.analysis import Analysis
from app.models.document import Document
from app.models.issue import Issue
from app.models.requirement import Requirement
from app.models.user import User
from app.models.user_preference import UserPreference


@dataclass(frozen=True)
class DocumentStorageRef:
    id: uuid.UUID
    storage_path: str


class PrivacyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_preferences(self, *, owner_id: uuid.UUID) -> UserPreference | None:
        return await self._session.get(UserPreference, owner_id)

    async def upsert_preferences(
        self, *, owner_id: uuid.UUID, history_retention_days: int | None
    ) -> UserPreference:
        row = await self.get_preferences(owner_id=owner_id)
        if row is None:
            row = UserPreference(owner_id=owner_id, history_retention_days=history_retention_days)
            self._session.add(row)
        else:
            row.history_retention_days = history_retention_days
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_users_with_retention(self) -> list[UserPreference]:
        result = await self._session.execute(
            select(UserPreference).where(UserPreference.history_retention_days.is_not(None))
        )
        return list(result.scalars().all())

    async def list_owned_storage_refs(self, *, owner_id: uuid.UUID) -> list[DocumentStorageRef]:
        result = await self._session.execute(
            select(Document.id, Document.storage_path).where(Document.owner_id == owner_id)
        )
        return [DocumentStorageRef(id=row[0], storage_path=row[1]) for row in result.all()]

    async def list_analyses_before(
        self, *, owner_id: uuid.UUID, cutoff: datetime
    ) -> list[Analysis]:
        result = await self._session.execute(
            select(Analysis)
            .where(Analysis.owner_id == owner_id, Analysis.created_at < cutoff)
            .order_by(Analysis.created_at.asc(), Analysis.id.asc())
        )
        return list(result.scalars().all())

    async def document_refs_purgeable_with_analyses(
        self, *, owner_id: uuid.UUID, analysis_ids: set[uuid.UUID]
    ) -> list[DocumentStorageRef]:
        if not analysis_ids:
            return []
        candidate_rows = await self._session.execute(
            select(Document.id, Document.storage_path)
            .join(Analysis, Analysis.document_id == Document.id)
            .where(
                Document.owner_id == owner_id,
                Analysis.owner_id == owner_id,
                Analysis.id.in_(analysis_ids),
            )
            .distinct()
        )
        refs: list[DocumentStorageRef] = []
        for document_id, storage_path in candidate_rows.all():
            remaining = (
                await self._session.execute(
                    select(func.count())
                    .select_from(Analysis)
                    .where(
                        Analysis.document_id == document_id,
                        Analysis.owner_id == owner_id,
                        Analysis.id.not_in(analysis_ids),
                    )
                )
            ).scalar_one()
            if remaining == 0:
                refs.append(DocumentStorageRef(id=document_id, storage_path=storage_path))
        return refs

    async def delete_documents_by_ids(
        self, *, owner_id: uuid.UUID, document_ids: set[uuid.UUID]
    ) -> int:
        if not document_ids:
            return 0
        result = await self._session.execute(
            delete(Document).where(Document.owner_id == owner_id, Document.id.in_(document_ids))
        )
        await self._session.flush()
        rowcount: int = result.rowcount  # type: ignore[attr-defined]
        return rowcount

    async def delete_analyses_by_ids(
        self, *, owner_id: uuid.UUID, analysis_ids: set[uuid.UUID]
    ) -> int:
        if not analysis_ids:
            return 0
        result = await self._session.execute(
            delete(Analysis).where(Analysis.owner_id == owner_id, Analysis.id.in_(analysis_ids))
        )
        await self._session.flush()
        rowcount: int = result.rowcount  # type: ignore[attr-defined]
        return rowcount

    async def load_export_user(self, *, owner_id: uuid.UUID) -> User | None:
        return await self._session.get(User, owner_id)

    async def load_export_analyses(self, *, owner_id: uuid.UUID) -> list[Analysis]:
        result = await self._session.execute(
            select(Analysis)
            .where(Analysis.owner_id == owner_id)
            .options(
                selectinload(Analysis.document),
                selectinload(Analysis.requirements).selectinload(Requirement.issues),
            )
            .order_by(Analysis.created_at.asc(), Analysis.id.asc())
        )
        return list(result.scalars().all())

    async def load_export_documents(self, *, owner_id: uuid.UUID) -> list[Document]:
        result = await self._session.execute(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
        return list(result.scalars().all())

    async def load_export_credentials(self, *, owner_id: uuid.UUID) -> list[AICredential]:
        result = await self._session.execute(
            select(AICredential)
            .where(AICredential.owner_id == owner_id)
            .order_by(AICredential.created_at.asc(), AICredential.id.asc())
        )
        return list(result.scalars().all())

    async def count_owned_rows(self, *, owner_id: uuid.UUID) -> dict[str, int]:
        return {
            "analyses": (
                await self._session.execute(
                    select(func.count()).select_from(Analysis).where(Analysis.owner_id == owner_id)
                )
            ).scalar_one(),
            "requirements": (
                await self._session.execute(
                    select(func.count())
                    .select_from(Requirement)
                    .where(Requirement.owner_id == owner_id)
                )
            ).scalar_one(),
            "issues": (
                await self._session.execute(
                    select(func.count()).select_from(Issue).where(Issue.owner_id == owner_id)
                )
            ).scalar_one(),
            "documents": (
                await self._session.execute(
                    select(func.count()).select_from(Document).where(Document.owner_id == owner_id)
                )
            ).scalar_one(),
            "ai_provider_credentials": (
                await self._session.execute(
                    select(func.count())
                    .select_from(AICredential)
                    .where(AICredential.owner_id == owner_id)
                )
            ).scalar_one(),
            "user_preferences": (
                await self._session.execute(
                    select(func.count())
                    .select_from(UserPreference)
                    .where(UserPreference.owner_id == owner_id)
                )
            ).scalar_one(),
        }
