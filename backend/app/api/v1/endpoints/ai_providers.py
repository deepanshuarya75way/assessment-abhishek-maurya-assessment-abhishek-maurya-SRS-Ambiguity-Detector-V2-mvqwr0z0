"""Provider credential endpoints (API_CONTRACT §4.6 — vault CRUD + test).

Thin: guards → service → presenter. Identity-only on the safe list GET;
CSRF + default bucket on mutations; CSRF + the dedicated 10/min test bucket
on TEST (outbound calls are the expensive side). Plaintext keys travel ONLY
in inbound CREATE/ROTATE bodies — responses are presenter-allowlisted
metadata, and every id here is owner-scoped (foreign ids 404 like missing
ones — IDOR rule). Unknown providers fail as `400 validation_error` via the
request Literal; a stored-but-unregistered id would 500 in the presenter.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_verified_user, verified_user_guard
from app.api.v1.presenters import provider_response
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.ai_providers import (
    ProviderCreateRequest,
    ProviderMetadataResponse,
    ProviderTestResponse,
    ProviderUpdateRequest,
    RotateKeyRequest,
)
from app.services import ai_providers as provider_service
from app.services.auth import UserInfo

router = APIRouter(prefix="/ai/providers", tags=["ai-providers"])

# Guard built once; the test budget lambda resolves per-request (never frozen).
mutate_guard = verified_user_guard("ai_providers:mutate")
test_guard = verified_user_guard(
    "ai_providers:test", limit=lambda: get_settings().RATE_LIMIT_AI_TEST_PER_MINUTE
)


@router.get("", response_model=list[ProviderMetadataResponse])
async def list_providers(
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProviderMetadataResponse]:
    """Owned credentials, registry order then enabled-first then oldest."""
    rows = await provider_service.list_credentials(session, owner_id=user.id)
    return [provider_response(row) for row in rows]


@router.post("", response_model=ProviderMetadataResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreateRequest,
    user: Annotated[UserInfo, Depends(mutate_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderMetadataResponse:
    """Store a credential (always enabled, never default)."""
    row = await provider_service.create_credential(
        session, owner_id=user.id, provider=body.provider, label=body.label, api_key=body.api_key
    )
    return provider_response(row)


@router.post("/{credential_id}/test", response_model=ProviderTestResponse)
async def test_provider(
    credential_id: UUID,
    user: Annotated[UserInfo, Depends(test_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderTestResponse:
    """Live-check a key (always 200: a failed check is data, not an error)."""
    ok, models, latency_ms, error = await provider_service.test_credential(
        session, owner_id=user.id, credential_id=credential_id
    )
    return ProviderTestResponse(ok=ok, models=models, latency_ms=latency_ms, error=error)


@router.patch("/{credential_id}", response_model=ProviderMetadataResponse)
async def update_provider(
    credential_id: UUID,
    body: ProviderUpdateRequest,
    user: Annotated[UserInfo, Depends(mutate_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderMetadataResponse:
    """Update metadata (`label: null` clears; absent leaves)."""
    row = await provider_service.update_credential(
        session,
        owner_id=user.id,
        credential_id=credential_id,
        label=body.label,
        is_enabled=body.is_enabled,
        is_default=body.is_default,
        fallback_rank=body.fallback_rank,
        label_provided="label" in body.model_fields_set,
    )
    return provider_response(row)


@router.post("/{credential_id}/rotate-key", response_model=ProviderMetadataResponse)
async def rotate_provider_key(
    credential_id: UUID,
    body: RotateKeyRequest,
    user: Annotated[UserInfo, Depends(mutate_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderMetadataResponse:
    """Replace stored key material (test verdict cleared — unproven key)."""
    row = await provider_service.rotate_key(
        session, owner_id=user.id, credential_id=credential_id, api_key=body.api_key
    )
    return provider_response(row)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    credential_id: UUID,
    user: Annotated[UserInfo, Depends(mutate_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Delete a credential (ciphertext gone; nothing retained)."""
    await provider_service.delete_credential(session, owner_id=user.id, credential_id=credential_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
