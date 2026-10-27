"""System-level API models (health probes)."""

from typing import Literal

from pydantic import BaseModel

from app import __version__


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "srs-ambiguity-detector"
    version: str = __version__


class ReadyResponse(BaseModel):
    status: Literal["ready", "degraded"] = "ready"
    checks: dict[str, str] = {}
