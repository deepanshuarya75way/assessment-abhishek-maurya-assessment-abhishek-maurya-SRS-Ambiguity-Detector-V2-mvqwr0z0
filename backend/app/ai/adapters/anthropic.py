"""Anthropic adapter (`api.anthropic.com` Messages API).

`POST /v1/messages` for generation (top-level `system` + one user message —
the SAME versioned prompt text every other adapter sends), `GET /v1/models`
as the credential probe. The key travels in the `x-api-key` HEADER, never a
URL (SECURITY_SPEC §4: key material stays out of URLs), beside the pinned
`anthropic-version` header the API requires.

Anthropic shape notes: bad keys fail as 401 `authentication_error`, so the
shared core's default (401/403 → auth) is exactly right — no `_client_error`
override. Generation REQUIRES `max_tokens`; the 512/256 budgets match the
other adapters. Overload arrives as 529, inside the core's retried 5xx band.
"""

from time import perf_counter
from typing import Any

from app.ai.adapters.base import BaseAdapter
from app.ai.models import default_model, supported_models
from app.ai.prompts import (
    IMPROVEMENT_SYSTEM_PROMPT,
    OVERVIEW_SYSTEM_PROMPT,
    render_improvement,
    render_overview,
)
from app.ai.providers import (
    AITextResult,
    ImprovementPayload,
    OverviewPayload,
    ProviderAuthResult,
    ProviderHealth,
)
from app.ai.registry import PROVIDER_METADATA
from app.ai.sanitize import sanitize_ai_text
from app.core.config import get_settings

# Pinned API version (the documented stable baseline — generation + probe).
_ANTHROPIC_VERSION = "2023-06-01"
_OVERVIEW_MAX_TOKENS = 512
_IMPROVEMENT_MAX_TOKENS = 256
_GENERATION_TEMPERATURE = 0.2


class AnthropicProvider(BaseAdapter):
    id = "anthropic"
    display_name = PROVIDER_METADATA["anthropic"].display_name
    base_url = PROVIDER_METADATA["anthropic"].base_url

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"x-api-key": api_key, "anthropic-version": _ANTHROPIC_VERSION}

    async def validate_credentials(self, api_key: str) -> ProviderAuthResult:
        await self._probe(api_key)
        return ProviderAuthResult(ok=True, detail="Key accepted.")

    async def health_check(self, api_key: str) -> ProviderHealth:
        await self._probe(api_key)
        return ProviderHealth(ok=True, detail="Provider reachable.")

    async def _probe(self, api_key: str) -> None:
        """Model list: cheap, auth-proving, fixed-shape (no generation cost)."""
        await self._get_json(
            f"{self.base_url}/v1/models",
            headers=self._headers(api_key),
            timeout_s=get_settings().AI_DEFAULT_TIMEOUT_S,
        )

    async def list_models(self, api_key: str) -> list[str]:
        _ = api_key
        return list(supported_models(self.id))

    async def generate_overview(
        self, api_key: str, payload: OverviewPayload, *, timeout_s: int
    ) -> AITextResult:
        return await self._generate(
            api_key,
            system=OVERVIEW_SYSTEM_PROMPT,
            user_text=render_overview(payload),
            max_tokens=_OVERVIEW_MAX_TOKENS,
            timeout_s=timeout_s,
        )

    async def generate_improvement(
        self, api_key: str, payload: ImprovementPayload, *, timeout_s: int
    ) -> AITextResult:
        return await self._generate(
            api_key,
            system=IMPROVEMENT_SYSTEM_PROMPT,
            user_text=render_improvement(payload),
            max_tokens=_IMPROVEMENT_MAX_TOKENS,
            timeout_s=timeout_s,
        )

    async def _generate(
        self, api_key: str, *, system: str, user_text: str, max_tokens: int, timeout_s: int
    ) -> AITextResult:
        model = default_model(self.id)
        started = perf_counter()
        body = await self._post_json(
            f"{self.base_url}/v1/messages",
            headers=self._headers(api_key),
            payload={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": _GENERATION_TEMPERATURE,
                "system": system,
                "messages": [{"role": "user", "content": user_text}],
            },
            timeout_s=timeout_s,
        )
        latency_ms = int((perf_counter() - started) * 1000)
        text, response_model, usage = self._extract(body)
        return AITextResult(
            text=sanitize_ai_text(text),
            model=(response_model or model)[:128],
            latency_ms=latency_ms,
            usage=usage,
        )

    def _extract(self, body: Any) -> tuple[str, str | None, dict[str, Any] | None]:
        """Join `content[]` text blocks (stop-reason/refusal responses carry
        no usable text → `bad_response`, never a guess)."""
        if not isinstance(body, dict):
            raise self._unexpected()
        content = body.get("content")
        if not isinstance(content, list) or not content:
            raise self._unexpected()
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and block["text"].strip()
        ]
        if not texts:
            raise self._unexpected()
        model = body.get("model")
        usage = body.get("usage")
        return (
            "\n".join(texts),
            model if isinstance(model, str) else None,
            dict(usage) if isinstance(usage, dict) else None,
        )


__all__ = ["AnthropicProvider"]
