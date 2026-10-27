"""Dashboard snapshot (API_CONTRACT §4.5 — Stage 11: one aggregate endpoint).

Thin: verified identity → service → response. Ownership-scoped (no `user_id`
param exists — the snapshot always describes the caller), deterministic per
(range, data, UTC day), bounded (fixed vocabularies + zero-filled trailing
window + 5 recent summaries). Empty accounts get zeros/empties/nulls, never
404. Unknown query params are ignored by FastAPI; a bad `range` is a `400
validation_error` like every other contract misuse.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_verified_user
from app.api.v1.presenters import dashboard_response
from app.core.database import get_session
from app.schemas.dashboard import DashboardResponse
from app.services import dashboard as dashboard_service
from app.services.auth import UserInfo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RangeParam = Literal["30d", "12w"]


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    range: Annotated[RangeParam, Query()] = "30d",
) -> DashboardResponse:
    """Account-wide aggregate snapshot (contract §4.5)."""
    data = await dashboard_service.get_dashboard(session, owner_id=user.id, window=range)
    return dashboard_response(data)
