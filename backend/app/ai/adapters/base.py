"""Shared HTTP core for provider adapters (AI_PROVIDER_SPEC §2).

Every adapter gets: explicit per-call timeouts (clamped to the configured
max), retry ONLY on 429/5xx (max 2, jittered backoff — never on auth,
timeout, or transport failures), and normalized `ProviderError` failures
(raw provider bodies are NEVER propagated or logged).

Adapters log NOTHING here: request headers carry the plaintext key, so the
quietest core is the safest one. The enhancement service logs provider id +
latency + error code (never prompts, outputs, or keys).
"""

import asyncio
import random
from typing import Any

import httpx

from app.ai.providers import AIProvider, ProviderError
from app.core.config import get_settings

# ABC contract: retry ONLY on 429/5xx, max 2 retries (3 attempts total).
MAX_RETRIES = 2
_BACKOFF_BASE_S = 0.5
_BACKOFF_JITTER_S = 0.25


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff + jitter for retry `attempt` (1-based)."""
    base = _BACKOFF_BASE_S * (2 ** (attempt - 1))
    jitter = random.uniform(0.0, _BACKOFF_JITTER_S)  # noqa: S311 — backoff jitter, not cryptography
    return float(base + jitter)


class BaseAdapter(AIProvider):
    """`AIProvider` + HTTP plumbing. Subclasses set `id`/`display_name`/
    `base_url` (class attrs, mirroring the registry metadata) and implement
    the five ABC methods via `_post_json`/`_get_json`.

    `client` is the test seam: production passes none (an ephemeral client
    per call — adapters are stateless singletons), tests inject an
    `httpx.AsyncClient` on a `MockTransport`. No live network in tests, ever.
    """

    id: str
    display_name: str
    base_url: str

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    # -- timeouts -------------------------------------------------------
    @staticmethod
    def _clamp_timeout(timeout_s: int) -> float:
        """Clamp a caller timeout into [1, AI_MAX_TIMEOUT_S] (floor 1 s so a
        zero/negative timeout fails closed-fast, never hangs unbounded)."""
        return float(min(max(1, timeout_s), get_settings().AI_MAX_TIMEOUT_S))

    def _budget(self, timeout_s: int) -> httpx.Timeout:
        # Named `time_budget` (not `timeout`) for the ASYNC109 lint rule —
        # httpx per-request budgets are exactly the sanctioned pattern.
        return httpx.Timeout(self._clamp_timeout(timeout_s))

    # -- transport ------------------------------------------------------
    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_s: int,
    ) -> Any:
        time_budget = self._budget(timeout_s)
        if self._client is not None:
            return await self._post_with_client(
                self._client, url, headers=headers, payload=payload, time_budget=time_budget
            )
        async with httpx.AsyncClient(timeout=time_budget, follow_redirects=False) as client:
            return await self._post_with_client(
                client, url, headers=headers, payload=payload, time_budget=time_budget
            )

    async def _post_with_client(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        time_budget: httpx.Timeout,
    ) -> Any:
        attempts = 0
        while True:
            try:
                response = await client.post(
                    url, headers=headers, json=payload, timeout=time_budget
                )
            except httpx.TimeoutException:
                raise ProviderError(
                    "timeout", f"{self.display_name} timed out. Try again later."
                ) from None
            except httpx.TransportError:
                # DNS, connect, TLS — the provider is unreachable from here.
                raise ProviderError(
                    "unavailable", f"{self.display_name} is unavailable right now."
                ) from None
            status = response.status_code
            if status == 402:
                raise ProviderError(
                    "quota",
                    f"{self.display_name} requires available billing or credits for this request.",
                )
            if status == 429 or 500 <= status <= 599:
                if attempts < MAX_RETRIES:
                    attempts += 1
                    await asyncio.sleep(_backoff_delay(attempts))
                    continue
                if status == 429:
                    raise ProviderError(
                        "quota",
                        f"{self.display_name} rate limit or quota exceeded. Try again later.",
                    )
                raise ProviderError("unavailable", f"{self.display_name} is unavailable right now.")
            if status in (401, 403):
                raise ProviderError(
                    "auth",
                    f"{self.display_name} rejected the API key. Check the key in Settings.",
                )
            if 200 <= status <= 299:
                return self._parse_json(response)
            # 400/404/other-4xx + 3xx (redirects disabled): the request the
            # adapter built is fixed-shape, so anything else is unexpected —
            # subclasses with key-shaped 4xx (Gemini's 400) override the hook.
            raise self._client_error(status)

    async def _get_json(self, url: str, *, headers: dict[str, str], timeout_s: int) -> Any:
        """GET twin of `_post_json` (credential probes) — same retry/map rules."""
        time_budget = self._budget(timeout_s)
        if self._client is not None:
            return await self._get_with_client(
                self._client, url, headers=headers, time_budget=time_budget
            )
        async with httpx.AsyncClient(timeout=time_budget, follow_redirects=False) as client:
            return await self._get_with_client(
                client, url, headers=headers, time_budget=time_budget
            )

    async def _get_with_client(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str],
        time_budget: httpx.Timeout,
    ) -> Any:
        attempts = 0
        while True:
            try:
                response = await client.get(url, headers=headers, timeout=time_budget)
            except httpx.TimeoutException:
                raise ProviderError(
                    "timeout", f"{self.display_name} timed out. Try again later."
                ) from None
            except httpx.TransportError:
                raise ProviderError(
                    "unavailable", f"{self.display_name} is unavailable right now."
                ) from None
            status = response.status_code
            if status == 402:
                raise ProviderError(
                    "quota",
                    f"{self.display_name} requires available billing or credits for this request.",
                )
            if status == 429 or 500 <= status <= 599:
                if attempts < MAX_RETRIES:
                    attempts += 1
                    await asyncio.sleep(_backoff_delay(attempts))
                    continue
                if status == 429:
                    raise ProviderError(
                        "quota",
                        f"{self.display_name} rate limit or quota exceeded. Try again later.",
                    )
                raise ProviderError("unavailable", f"{self.display_name} is unavailable right now.")
            if status in (401, 403):
                raise ProviderError(
                    "auth",
                    f"{self.display_name} rejected the API key. Check the key in Settings.",
                )
            if 200 <= status <= 299:
                return self._parse_json(response)
            raise self._client_error(status)

    # -- shaping hooks --------------------------------------------------
    def _client_error(self, status: int) -> ProviderError:
        """4xx/3xx that isn't auth/quota: unexpected provider response."""
        _ = status
        return ProviderError(
            "bad_response", f"{self.display_name} returned an unexpected response."
        )

    def _parse_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise ProviderError(
                "bad_response", f"{self.display_name} returned an unexpected response."
            ) from None

    def _unexpected(self) -> ProviderError:
        """Well-formed HTTP, unusable shape (missing choices/candidates/...)."""
        return ProviderError(
            "bad_response", f"{self.display_name} returned an unexpected response."
        )
