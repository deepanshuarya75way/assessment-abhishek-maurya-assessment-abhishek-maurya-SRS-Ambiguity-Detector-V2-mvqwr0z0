"""Readiness aggregation — the canonical minimal service (API → service → repository).

Infrastructure exception: a probe is not part of any request transaction, so it
acquires its own short-lived session. Business services (Stage 04+) receive the
request-scoped session via DI instead. A probe must never raise.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.repositories.system import SystemRepository

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReadinessReport:
    status: Literal["ready", "degraded"]
    checks: dict[str, str] = field(default_factory=dict)


async def get_readiness() -> ReadinessReport:
    """Aggregate dependency health. Unconfigured → ready/not_configured; any
    failure → degraded/error. Details are logged server-side, never returned."""
    try:
        factory = get_session_factory()
    except RuntimeError:
        return ReadinessReport(status="ready", checks={"database": "not_configured"})
    try:
        async with factory() as session:
            await SystemRepository(session).ping()
    except Exception:
        logger.warning("Readiness database probe failed (details withheld).")
        return ReadinessReport(status="degraded", checks={"database": "error"})
    return ReadinessReport(status="ready", checks={"database": "ok"})
