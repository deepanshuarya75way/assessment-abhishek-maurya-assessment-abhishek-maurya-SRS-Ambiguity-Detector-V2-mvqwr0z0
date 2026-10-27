"""Provider abstraction (AI_PROVIDER_SPEC §2–§3 — binding interface).

Stage 12 shipped this vocabulary (adapters arrived in Stage 14): payload
models carry the §3 SHAPES (ids, caps, finding summaries) for the versioned
prompts (`app.ai.prompts`) and the enhancement service. All provider
failures normalize to `ProviderError` (raw provider bodies are NEVER
propagated).
"""

from abc import ABC, abstractmethod
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ProviderErrorCode = Literal["auth", "quota", "timeout", "bad_response", "unavailable"]


class ProviderError(Exception):
    """Normalized provider failure: machine code + user-safe message.

    Adapters MUST sanitize here — `user_message` may reach API responses.
    Never include keys, headers, request bodies, or raw provider text.
    """

    def __init__(self, code: ProviderErrorCode, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


class ProviderAuthResult(BaseModel):
    """Outcome of a credential proof-check (key accepted or not)."""

    ok: bool
    detail: str = ""


class ProviderHealth(BaseModel):
    """Outcome of a lightweight liveness probe with a stored key."""

    ok: bool
    detail: str = ""


class FindingSummary(BaseModel):
    """One deterministic finding, minimized for AI context (§3)."""

    category: str = Field(max_length=64)
    severity: str = Field(max_length=16)
    phrase: str = Field(max_length=500)
    reason: str = Field(max_length=1000)


class OverviewPayload(BaseModel):
    """Deterministic context for an analysis overview (§3) — summaries, NOT
    full raw text by default. Consumed by the enhancement service."""

    analysis_id: UUID
    score: int | None = None
    band: str | None = None
    top_findings: list[FindingSummary] = Field(default_factory=list, max_length=12)
    requirements_count: int = 0
    issues_count: int = 0


class ImprovementPayload(BaseModel):
    """One requirement + its findings for a rewrite suggestion (§3)."""

    requirement_text: str = Field(max_length=4000)
    findings: list[FindingSummary] = Field(default_factory=list, max_length=8)


class AITextResult(BaseModel):
    """Constrained AI text output — UNTRUSTED until sanitized at render."""

    text: str = Field(max_length=8000)
    model: str = Field(max_length=128)
    latency_ms: int = Field(ge=0)
    usage: dict[str, Any] | None = None


class AIProvider(ABC):
    """One AI backend. `base_url` is an allowlisted constant per provider —
    user-supplied hosts are never accepted (SSRF rule, §13). Timeouts cap at
    60 s; retries (429/5xx only, jittered, max 2) live in the adapters."""

    id: str
    display_name: str
    base_url: str

    @abstractmethod
    async def validate_credentials(self, api_key: str) -> ProviderAuthResult:
        """Prove a key works (creation-time check in the end-state flow)."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self, api_key: str) -> ProviderHealth:
        """Lightweight liveness probe with a stored key (test endpoint)."""
        raise NotImplementedError

    @abstractmethod
    async def list_models(self, api_key: str) -> list[str]:
        """Usable model ids for this key (test endpoint + Stage 19)."""
        raise NotImplementedError

    @abstractmethod
    async def generate_overview(
        self, api_key: str, payload: OverviewPayload, *, timeout_s: int
    ) -> AITextResult:
        """Analysis overview text (the enhancement service calls this)."""
        raise NotImplementedError

    @abstractmethod
    async def generate_improvement(
        self, api_key: str, payload: ImprovementPayload, *, timeout_s: int
    ) -> AITextResult:
        """Per-requirement rewrite suggestion (the enhancement service calls this)."""
        raise NotImplementedError
