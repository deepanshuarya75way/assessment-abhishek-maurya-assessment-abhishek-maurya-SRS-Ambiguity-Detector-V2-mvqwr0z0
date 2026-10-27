"""Google Gemini adapter (`generativelanguage.googleapis.com` REST).

`POST /v1beta/models/{model}:generateContent` for generation (system
instruction + one user part — the SAME versioned prompt text every other
adapter sends), `GET /v1beta/models?pageSize=1` as the credential probe.
The key travels in the `x-goog-api-key` HEADER, never the `?key=` query
string (query keys leak into proxy logs and error strings — SECURITY_SPEC
§4: key material stays out of URLs).

Gemini shape notes: an invalid key fails the probe AND generation with 400
(not 401), so `_client_error` maps 400 → auth; content-safety blocks arrive
as 200s without usable parts, which `_extract` reports as `bad_response`.
"""

from time import perf_counter
from typing import Any
from urllib.parse import quote

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
    ProviderError,
    ProviderHealth,
)
from app.ai.registry import PROVIDER_METADATA
from app.ai.sanitize import sanitize_ai_text
from app.core.config import get_settings

_OVERVIEW_MAX_TOKENS = 512
_IMPROVEMENT_MAX_TOKENS = 256
_GENERATION_TEMPERATURE = 0.2


class GeminiProvider(BaseAdapter):
    id = "gemini"
    display_name = PROVIDER_METADATA["gemini"].display_name
    base_url = PROVIDER_METADATA["gemini"].base_url

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"x-goog-api-key": api_key}

    def _client_error(self, status: int) -> ProviderError:
        # Gemini reports bad keys as 400 INVALID_ARGUMENT ("API key not
        # valid") — on our fixed-shape requests a 400 is a key problem, not
        # a payload problem, so the user gets the key-check message (and the
        # enhancement chain advances instead of retrying pointlessly).
        if status == 400:
            return ProviderError(
                "auth",
                f"{self.display_name} rejected the API key. Check the key in Settings.",
            )
        return super()._client_error(status)

    async def validate_credentials(self, api_key: str) -> ProviderAuthResult:
        await self._probe(api_key)
        return ProviderAuthResult(ok=True, detail="Key accepted.")

    async def health_check(self, api_key: str) -> ProviderHealth:
        await self._probe(api_key)
        return ProviderHealth(ok=True, detail="Provider reachable.")

    async def _probe(self, api_key: str) -> None:
        """One-model list page: cheap, auth-proving, fixed-shape."""
        await self._get_json(
            f"{self.base_url}/v1beta/models?pageSize=1",
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
        models = [default_model(self.id)]
        for m in supported_models(self.id):
            if m not in models:
                models.append(m)
        last_error: ProviderError | None = None
        for model in models:
            started = perf_counter()
            try:
                body = await self._post_json(
                    f"{self.base_url}/v1beta/models/{quote(model, safe='')}:generateContent",
                    headers=self._headers(api_key),
                    payload={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"parts": [{"text": user_text}]}],
                        "generationConfig": {
                            "temperature": _GENERATION_TEMPERATURE,
                            "maxOutputTokens": max_tokens,
                        },
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
            except ProviderError as exc:
                if exc.code == "quota":
                    last_error = exc
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise self._unexpected()

    def _extract(self, body: Any) -> tuple[str, str | None, dict[str, Any] | None]:
        """Join `candidates[0].content.parts[].text` (safety-blocked or empty
        responses have no usable parts → `bad_response`, never a guess)."""
        if not isinstance(body, dict):
            raise self._unexpected()
        candidates = body.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise self._unexpected()
        first = candidates[0]
        if not isinstance(first, dict):
            raise self._unexpected()
        content = first.get("content")
        if not isinstance(content, dict):
            raise self._unexpected()
        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise self._unexpected()
        texts = [
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
        ]
        if not texts:
            raise self._unexpected()
        model = body.get("model")
        usage = body.get("usageMetadata")
        return (
            "\n".join(texts),
            model if isinstance(model, str) else None,
            dict(usage) if isinstance(usage, dict) else None,
        )


__all__ = ["GeminiProvider"]
