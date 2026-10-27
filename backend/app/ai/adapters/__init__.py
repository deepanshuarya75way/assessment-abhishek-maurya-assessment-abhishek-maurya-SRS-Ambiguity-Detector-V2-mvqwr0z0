"""Production provider adapters (all six since Stage 18).

`BUILTIN_ADAPTERS` holds one stateless singleton per provider;
`registry.resolve_adapter` serves these unless a test fake shadows the id.
"""

from app.ai.adapters.anthropic import AnthropicProvider
from app.ai.adapters.gemini import GeminiProvider
from app.ai.adapters.groq import GroqProvider
from app.ai.adapters.huggingface import HuggingFaceProvider
from app.ai.adapters.openai import OpenAIProvider
from app.ai.adapters.openrouter import OpenRouterProvider
from app.ai.providers import AIProvider

BUILTIN_ADAPTERS: dict[str, AIProvider] = {
    adapter.id: adapter
    for adapter in (
        GeminiProvider(),
        GroqProvider(),
        OpenAIProvider(),
        AnthropicProvider(),
        OpenRouterProvider(),
        HuggingFaceProvider(),
    )
}

__all__ = [
    "BUILTIN_ADAPTERS",
    "AnthropicProvider",
    "GeminiProvider",
    "GroqProvider",
    "HuggingFaceProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
]
