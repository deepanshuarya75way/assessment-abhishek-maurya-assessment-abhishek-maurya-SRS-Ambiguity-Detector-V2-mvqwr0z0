"""Groq adapter: identity + allowlisted host over the shared chat shape."""

from app.ai.adapters.openai_compat import OpenAICompatAdapter
from app.ai.registry import PROVIDER_METADATA


class GroqProvider(OpenAICompatAdapter):
    id = "groq"
    display_name = PROVIDER_METADATA["groq"].display_name
    base_url = PROVIDER_METADATA["groq"].base_url


__all__ = ["GroqProvider"]
