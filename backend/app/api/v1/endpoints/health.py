"""Liveness + readiness probes (the project contract). No auth.

Thin by design: serialization here, aggregation in services/readiness.py.
"""

from fastapi import APIRouter

from app.schemas.system import LiveResponse, ReadyResponse
from app.services.readiness import get_readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """Process is up. Used by the frontend status card and orchestrators."""
    return LiveResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Dependencies reachable (see services/readiness.py). Never exposes details."""
    report = await get_readiness()
    return ReadyResponse(status=report.status, checks=report.checks)
