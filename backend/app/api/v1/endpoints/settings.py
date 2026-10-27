"""Own-profile endpoints (API_CONTRACT §4.7 — Stage 16).

Thin: guards → service → inline response (the `GET /auth/me` precedent — the
shape is a safe identity subset, never hashes/tokens/keys). Verified-only on
both verbs: profile reads/writes are app resources, not recovery flows.
No `{id}` anywhere, so no IDOR surface: the session IS the selector.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_verified_user, verified_user_guard
from app.core.database import get_session
from app.schemas.privacy import PrivacySettingsResponse, PrivacySettingsUpdateRequest
from app.schemas.settings import ProfileResponse, ProfileUpdateRequest
from app.services import privacy as privacy_service
from app.services import settings as settings_service
from app.services.auth import UserInfo

router = APIRouter(prefix="/settings", tags=["settings"])

mutate_guard = verified_user_guard("settings:mutate")


def _present(user: UserInfo) -> ProfileResponse:
    return ProfileResponse(
        email=user.email,
        display_name=user.display_name,
        is_verified=user.is_verified,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileResponse:
    """The caller's own profile (fresh row read, not session echo)."""
    fresh = await settings_service.get_profile(session, user_id=user.id)
    return _present(fresh)


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    user: Annotated[UserInfo, Depends(mutate_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileResponse:
    """Set (or clear via explicit null) the caller's display name."""
    fresh = await settings_service.update_display_name(
        session, user_id=user.id, display_name=body.display_name
    )
    return _present(fresh)


@router.get("/privacy", response_model=PrivacySettingsResponse)
async def get_privacy_settings(
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivacySettingsResponse:
    """The caller's enforced privacy lifecycle settings."""
    return await privacy_service.get_privacy_settings(session, owner_id=user.id)


@router.patch("/privacy", response_model=PrivacySettingsResponse)
async def update_privacy_settings(
    body: PrivacySettingsUpdateRequest,
    user: Annotated[UserInfo, Depends(mutate_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivacySettingsResponse:
    """Set or clear the caller's automatic history-retention window."""
    return await privacy_service.update_privacy_settings(
        session, owner_id=user.id, history_retention_days=body.history_retention_days
    )
