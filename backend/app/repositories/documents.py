"""`documents` persistence. SQLAlchemy lives here; no rules here.

Same conventions as `repositories/analysis.py`: ownership arrives from the
caller, `get_owned` doubles as the IDOR guard, no commits (the service's
@transactional boundary owns the transaction). Storage OBJECTS are not rows —
the service deletes the binary alongside the row (the DB cannot reach object
storage — DATABASE_SCHEMA §3.5).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.document import Document


class DocumentRepository:
    """`documents` rows (Stage 08 writes `ok` rows for analyzed uploads)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        id: uuid.UUID,
        owner_id: uuid.UUID,
        filename: str,
        file_type: str,
        mime_type: str,
        byte_size: int,
        sha256: str,
        storage_path: str,
        extracted_chars: int,
        extraction_status: str = "ok",
    ) -> Document:
        # `id` is service-generated (the storage key embeds it BEFORE the row
        # exists — no post-flush UPDATE).
        row = Document(
            id=id,
            owner_id=owner_id,
            filename=filename,
            file_type=file_type,
            mime_type=mime_type,
            byte_size=byte_size,
            sha256=sha256,
            storage_path=storage_path,
            extracted_chars=extracted_chars,
            extraction_status=extraction_status,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_owned(self, *, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        """One document iff owned (None covers missing AND foreign — IDOR)."""
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self, *, owner_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[Document], int]:
        """Newest-first page of owned documents + total (contract §3).

        Fixed order (`created_at` DESC + `id` DESC tiebreak — same idiom as
        the analysis history default); no filters in v1 (documents carry no
        band/score to slice by).
        """
        total = (
            await self._session.execute(
                select(func.count()).select_from(Document).where(Document.owner_id == owner_id)
            )
        ).scalar_one()
        result = await self._session.execute(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def count_referencing_analyses(self, *, document_id: uuid.UUID) -> int:
        """How many analyses still point at this document (orphan-cascade
        decision on analysis delete — shared documents survive)."""
        return (
            await self._session.execute(
                select(func.count())
                .select_from(Analysis)
                .where(Analysis.document_id == document_id)
            )
        ).scalar_one()

    async def delete(self, row: Document) -> None:
        """Delete an owned row (the service removes the storage object too)."""
        await self._session.delete(row)
        await self._session.flush()
