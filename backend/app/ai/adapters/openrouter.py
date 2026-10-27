"""OpenRouter adapter: chat shape + the spec'd `HTTP-Referer` header (§4)."""

from app.ai.adapters.openai_compat import OpenAICompatAdapter
from app.ai.registry import PROVIDER_METADATA
from app.core.config import get_settings


class OpenRouterProvider(OpenAICompatAdapter):
    id = "openrouter"
    display_name = PROVIDER_METADATA["openrouter"].display_name
    base_url = PROVIDER_METADATA["openrouter"].base_url

    def _extra_headers(self) -> dict[str, str]:
        # Spec §4: Referer = site URL (server config, never client input).
        return {"HTTP-Referer": get_settings().APP_BASE_URL}


__all__ = ["OpenRouterProvider"]
