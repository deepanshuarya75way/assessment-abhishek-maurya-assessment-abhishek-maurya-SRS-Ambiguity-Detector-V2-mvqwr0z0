"""`ai_provider_credentials` persistence. SQLAlchemy lives here; no rules here.

Ownership arrives from the caller (the service passes the session user id —
never a client-supplied id). Reads are owner-scoped (`get_owned` doubles as
the IDOR guard: no row, no oracle). Ciphertext is opaque TEXT here — the
vault owns its meaning. No commits here: the service's @transactional
boundary owns the transaction.
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_credential import AICredential


class AICredentialRepository:
    """Per-user ENCRYPTED provider keys (vault writes read through here)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        provider: str,
        label: str | None,
        encrypted_api_key: str,
        key_version: int,
        key_fingerprint: str,
        last4: str,
        last_test_status: str | None = None,
        last_tested_at: datetime | None = None,
    ) -> AICredential:
        row = AICredential(
            owner_id=owner_id,
            provider=provider,
            label=label,
            encrypted_api_key=encrypted_api_key,
            key_version=key_version,
            key_fingerprint=key_fingerprint,
            last4=last4,
            is_enabled=True,
            is_default=False,
            fallback_rank=0,
            last_test_status=last_test_status,
            last_tested_at=last_tested_at,
        )
        self._session.add(row)
        await self._session.flush()  # surfaces constraint violations inside the txn
        await self._session.refresh(row)
        return row

    async def get_owned(
        self, *, owner_id: uuid.UUID, credential_id: uuid.UUID
    ) -> AICredential | None:
        """One credential iff owned (None covers missing AND foreign — IDOR)."""
        result = await self._session.execute(
            select(AICredential).where(
                AICredential.id == credential_id, AICredential.owner_id == owner_id
            )
        )
        return result.scalar_one_or_none()

    async def list_owned(self, *, owner_id: uuid.UUID) -> list[AICredential]:
        """Every owned row, oldest first (the service applies registry order)."""
        result = await self._session.execute(
            select(AICredential)
            .where(AICredential.owner_id == owner_id)
            .order_by(AICredential.created_at.asc(), AICredential.id.asc())
        )
        return list(result.scalars().all())

    async def list_enabled_chain(self, *, owner_id: uuid.UUID) -> list[AICredential]:
        """Owned ENABLED rows in enhancement-chain order (Stage 14): the
        default first, then `fallback_rank` ascending, then oldest — the
        service tries them in this order (AI_PROVIDER_SPEC §5/§7)."""
        result = await self._session.execute(
            select(AICredential)
            .where(AICredential.owner_id == owner_id, AICredential.is_enabled)
            .order_by(
                AICredential.is_default.desc(),
                AICredential.fallback_rank.asc(),
                AICredential.created_at.asc(),
                AICredential.id.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_enabled(
        self, *, owner_id: uuid.UUID, provider: str, exclude_id: uuid.UUID | None = None
    ) -> AICredential | None:
        """The live row for (owner, provider), if any — the conflict pre-check."""
        filters = [
            AICredential.owner_id == owner_id,
            AICredential.provider == provider,
            AICredential.is_enabled,
        ]
        if exclude_id is not None:
            filters.append(AICredential.id != exclude_id)
        result = await self._session.execute(select(AICredential).where(*filters))
        return result.scalar_one_or_none()

    async def get_by_fingerprint(
        self,
        *,
        owner_id: uuid.UUID,
        provider: str,
        key_fingerprint: str,
        exclude_id: uuid.UUID | None = None,
    ) -> AICredential | None:
        """A row already storing this exact key material, if any (any state)."""
        filters = [
            AICredential.owner_id == owner_id,
            AICredential.provider == provider,
            AICredential.key_fingerprint == key_fingerprint,
        ]
        if exclude_id is not None:
            filters.append(AICredential.id != exclude_id)
        result = await self._session.execute(select(AICredential).where(*filters))
        return result.scalar_one_or_none()

    async def clear_default(self, *, owner_id: uuid.UUID, exclude_id: uuid.UUID) -> None:
        """Unset every other default for the owner (single UPDATE — the
        partial unique index makes concurrent double-defaults impossible)."""
        await self._session.execute(
            update(AICredential)
            .where(
                AICredential.owner_id == owner_id,
                AICredential.is_default,
                AICredential.id != exclude_id,
            )
            .values(is_default=False)
        )
        await self._session.flush()

    async def record_test_result(
        self, *, credential_id: uuid.UUID, status: str, tested_at: datetime
    ) -> None:
        """Stamp a completed test verdict (`ok`/`failed`, app-clock instant —
        the check ran in this process, so its clock is the honest one)."""
        await self._session.execute(
            update(AICredential)
            .where(AICredential.id == credential_id)
            .values(last_test_status=status, last_tested_at=tested_at)
        )
        await self._session.flush()

    async def delete(self, row: AICredential) -> None:
        """Delete the row (ciphertext gone; nothing retained, no soft-delete)."""
        await self._session.delete(row)
        await self._session.flush()
