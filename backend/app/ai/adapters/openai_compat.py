"""OpenAI-compatible chat adapter (openai, groq, openrouter).

One REST shape serves all three: `POST {base}/v1/chat/completions` with
`Authorization: Bearer`, `GET {base}/v1/models` as the credential probe.
Subclasses differ ONLY in identity + base URL + model table row (+ the
OpenRouter `HTTP-Referer` header, via `_extra_headers`). No `if provider ==`
anywhere — the registry resolves the subclass, the subclass carries the facts.
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
from app.ai.sanitize import sanitize_ai_text
from app.core.config import get_settings

# Token budgets (AI_PROVIDER_SPEC §9): overviews are 2-4 sentences,
# improvements a single statement — tight caps, partial text still kept.
_OVERVIEW_MAX_TOKENS = 512
_IMPROVEMENT_MAX_TOKENS = 256
_GENERATION_TEMPERATURE = 0.2


class OpenAICompatAdapter(BaseAdapter):
    """Full ABC over the OpenAI chat-completions shape (subclass per host)."""

    def _extra_headers(self) -> dict[str, str]:
        return {}

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", **self._extra_headers()}

    # -- credential proof + liveness ------------------------------------
    async def validate_credentials(self, api_key: str) -> ProviderAuthResult:
        await self._probe(api_key)
        return ProviderAuthResult(ok=True, detail="Key accepted.")

    async def health_check(self, api_key: str) -> ProviderHealth:
        await self._probe(api_key)
        return ProviderHealth(ok=True, detail="Provider reachable.")

    async def _probe(self, api_key: str) -> None:
        """`GET /v1/models`: cheap, auth-proving, fixed-shape. Failures raise
        the normalized `ProviderError` (the TEST endpoint renders `user_message`)."""
        await self._get_json(
            f"{self.base_url}/v1/models",
            headers=self._headers(api_key),
            timeout_s=get_settings().AI_DEFAULT_TIMEOUT_S,
        )

    async def list_models(self, api_key: str) -> list[str]:
        """Curated allowlist (models.py) — NO network: stable, instant, and
        honest about being a discovery hint rather than a capability probe."""
        _ = api_key
        return list(supported_models(self.id))

    # -- generation -----------------------------------------------------
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
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(api_key),
            payload={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                "temperature": _GENERATION_TEMPERATURE,
                "max_tokens": max_tokens,
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
        """`choices[0].message.content` (+ model echo + usage iff dict-shaped).

        Anything else-shaped raises `bad_response` — adapters never guess at
        provider envelopes, and never propagate what they can't parse.
        """
        if not isinstance(body, dict):
            raise self._unexpected()
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise self._unexpected()
        first = choices[0]
        if not isinstance(first, dict):
            raise self._unexpected()
        message = first.get("message")
        if not isinstance(message, dict):
            raise self._unexpected()
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise self._unexpected()
        model = body.get("model")
        usage = body.get("usage")
        return (
            content,
            model if isinstance(model, str) else None,
            dict(usage) if isinstance(usage, dict) else None,
        )


__all__ = ["OpenAICompatAdapter"]
