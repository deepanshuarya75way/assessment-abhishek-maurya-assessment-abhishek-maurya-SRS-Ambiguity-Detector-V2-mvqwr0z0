"""Privacy/data lifecycle endpoints (API_CONTRACT §4.7 — Stage 23)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_verified_user, verified_user_guard
from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import (
    create_privacy_export_token,
    decode_privacy_export_token,
    utcnow,
)
from app.exceptions import InvalidTokenError
from app.schemas.privacy import (
    PrivacyExportResponse,
    PrivacyExportTicketResponse,
    PrivacyPurgeRequest,
    PrivacyPurgeResponse,
)
from app.services import privacy as privacy_service
from app.services.auth import UserInfo

router = APIRouter(prefix="/privacy", tags=["privacy"])

export_guard = verified_user_guard("privacy:export")
purge_guard = verified_user_guard("privacy:purge")
_EXPORT_TTL_MINUTES = 15


@router.post(
    "/export",
    response_model=PrivacyExportTicketResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_privacy_export(
    user: Annotated[UserInfo, Depends(export_guard)],
) -> PrivacyExportTicketResponse:
    """Create a short-lived, owner-bound export ticket.

    Export material is generated on the GET using the live owner-scoped rows;
    no background job or server-side export artifact is claimed.
    """
    export_id = create_privacy_export_token(user.id, expires_minutes=_EXPORT_TTL_MINUTES)
    expires_at = utcnow() + timedelta(minutes=_EXPORT_TTL_MINUTES)
    prefix = get_settings().API_V1_PREFIX.rstrip("/")
    return PrivacyExportTicketResponse(
        export_id=export_id,
        download_url=f"{prefix}/privacy/export/{export_id}",
        expires_at=expires_at,
    )


@router.get("/export/{export_id}", response_model=PrivacyExportResponse)
async def download_privacy_export(
    export_id: str,
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> PrivacyExportResponse:
    """Return the caller's allowlisted data export.

    The path token is signed and expiring, but the session must also match the
    token owner. Export never includes secrets, token hashes, ciphertext, or
    storage paths.
    """
    token_owner = decode_privacy_export_token(export_id)
    if token_owner != user.id:
        raise InvalidTokenError("This export link is invalid.")
    response.headers["content-disposition"] = 'attachment; filename="srs-privacy-export.json"'
    return await privacy_service.build_privacy_export(session, owner_id=user.id)


@router.post("/purge-history", response_model=PrivacyPurgeResponse)
async def purge_history(
    body: PrivacyPurgeRequest,
    user: Annotated[UserInfo, Depends(purge_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivacyPurgeResponse:
    """Purge owned analysis history older than an explicit or configured window."""
    return await privacy_service.purge_history(
        session, owner_id=user.id, older_than_days=body.older_than_days
    )
