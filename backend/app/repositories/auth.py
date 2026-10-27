"""Auth data access: users + token tables. SQLAlchemy lives here; no rules here."""

import datetime as dt
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_tokens import (
    PasswordResetToken,
    RefreshToken,
)
from app.models.user import User


class UserRepository:
    """User rows (callers normalize email first; uniqueness is app + DB)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, *, email: str, display_name: str, password_hash: str) -> User:
        user = User(email=email, display_name=display_name, password_hash=password_hash)
        self._session.add(user)
        await self._session.flush()  # surfaces UNIQUE violations inside the txn
        return user

    async def set_verified(self, user: User) -> None:
        user.is_verified = True
        await self._session.flush()

    async def set_password_hash(self, user: User, new_hash: str) -> None:
        user.password_hash = new_hash
        await self._session.flush()

    async def set_display_name(self, user: User, display_name: str | None) -> None:
        user.display_name = display_name
        await self._session.flush()

    async def record_login(self, user: User, at: dt.datetime) -> None:
        user.last_login_at = at
        await self._session.flush()

    async def delete(self, user: User) -> None:
        await self._session.delete(user)  # FK cascades purge tokens + owned rows


class RefreshTokenRepository:
    """Refresh sessions + rotation bookkeeping (reuse detection lives in service)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        token_hash: str,
        family_id: uuid.UUID,
        expires_at: dt.datetime,
        user_agent: str | None,
        ip_hash: str | None,
    ) -> RefreshToken:
        row = RefreshToken(
            owner_id=owner_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_rotated(self, row: RefreshToken, *, new_hash: str, now: dt.datetime) -> None:
        row.revoked_at = now
        row.replaced_by_hash = new_hash
        await self._session.flush()

    async def revoke(self, row: RefreshToken, *, now: dt.datetime) -> None:
        row.revoked_at = now  # replaced_by_hash stays NULL = logged-out marker
        await self._session.flush()

    async def revoke_family(self, family_id: uuid.UUID, *, now: dt.datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_all_for_owner(self, owner_id: uuid.UUID, *, now: dt.datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.owner_id == owner_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )


class PasswordResetTokenRepository:
    """Single-use reset tokens (consumed rows are kept as audit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, owner_id: uuid.UUID, token_hash: str, expires_at: dt.datetime
    ) -> PasswordResetToken:
        row = PasswordResetToken(owner_id=owner_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        result = await self._session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_consumed(self, row: PasswordResetToken, *, now: dt.datetime) -> None:
        row.consumed_at = now
        await self._session.flush()

    async def delete_pending_for_owner(self, owner_id: uuid.UUID) -> None:
        """Drop superseded unconsumed tokens (consumed rows stay as audit)."""
        await self._session.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.owner_id == owner_id,
                PasswordResetToken.consumed_at.is_(None),
            )
        )
