"""OpenAI adapter: identity + allowlisted host over the shared chat shape."""

from app.ai.adapters.openai_compat import OpenAICompatAdapter
from app.ai.registry import PROVIDER_METADATA


class OpenAIProvider(OpenAICompatAdapter):
    id = "openai"
    display_name = PROVIDER_METADATA["openai"].display_name
    base_url = PROVIDER_METADATA["openai"].base_url


__all__ = ["OpenAIProvider"]
