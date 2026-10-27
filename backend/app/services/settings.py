"""Own-profile reads/writes (API_CONTRACT §4.7 — Stage 16).

Identity-only: the caller IS the row (a verified guard sits upstream), so
there is no `{id}` to owner-check — a session whose row vanished (deleted
elsewhere) or deactivated reads `401 unauthenticated`, never 404/500.
Display names are cosmetic only: never logged, never used for lookups.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.exceptions import UnauthorizedError
from app.repositories.auth import UserRepository
from app.services.auth import UserInfo
from app.services.transactions import transactional

logger = get_logger(__name__)


async def get_profile(session: AsyncSession, *, user_id: uuid.UUID) -> UserInfo:
    """Re-read the caller's row (guards see session identity; this sees the row)."""
    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError()
    return UserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_verified=user.is_verified,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@transactional
async def update_display_name(
    session: AsyncSession, *, user_id: uuid.UUID, display_name: str | None
) -> UserInfo:
    """Set (or clear, via null) the caller's display name. Cosmetic only."""
    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError()
    await users.set_display_name(user, display_name)
    logger.info("profile display name updated user_id=%s", user.id)
    return UserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_verified=user.is_verified,
        is_active=user.is_active,
        created_at=user.created_at,
    )
