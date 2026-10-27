"""Provider registry (AI_PROVIDER_SPEC §4): static metadata + adapter seam.

Metadata is trusted server-side data — `base_url` values are allowlisted
constants (never user input: SSRF rule) and display names live here so API
responses can stay on stable machine ids. Production adapters ship in
`app.ai.adapters` (all six providers since Stage 18). Runtime code resolves
via `resolve_adapter` (registered fake wins, else the builtin singleton,
else None for a not-yet-wired future provider); `get_adapter` stays the RAW
seam (fakes/tests only) so suites
never depend on builtins. Adding provider #7 = adapter + metadata row +
model-table row + docs + tests — no router, service, or rendering changes.
"""

from dataclasses import dataclass

from app.ai.providers import AIProvider

# Registry order (§4 table) — doubles as the user-facing list order.
PROVIDER_IDS = ("gemini", "groq", "openai", "anthropic", "openrouter", "huggingface")

PROVIDER_ORDER = {provider_id: index for index, provider_id in enumerate(PROVIDER_IDS)}


@dataclass(frozen=True)
class ProviderMetadata:
    """Public, non-secret provider facts (safe to log and to document)."""

    id: str
    display_name: str
    base_url: str


PROVIDER_METADATA: dict[str, ProviderMetadata] = {
    "gemini": ProviderMetadata(
        id="gemini",
        display_name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com",
    ),
    # The shared OpenAI-compatible adapter appends /v1/...; include Groq's
    # /openai prefix here so the resulting endpoint paths are valid.
    "groq": ProviderMetadata(
        id="groq", display_name="Groq", base_url="https://api.groq.com/openai"
    ),
    "openai": ProviderMetadata(
        id="openai", display_name="OpenAI", base_url="https://api.openai.com"
    ),
    "anthropic": ProviderMetadata(
        id="anthropic", display_name="Anthropic", base_url="https://api.anthropic.com"
    ),
    "openrouter": ProviderMetadata(
        id="openrouter", display_name="OpenRouter", base_url="https://openrouter.ai/api"
    ),
    "huggingface": ProviderMetadata(
        id="huggingface",
        display_name="Hugging Face",
        # Inference Providers router (OpenAI-compatible). The legacy
        # api-inference host is retired (NXDOMAIN) — never point back.
        base_url="https://router.huggingface.co",
    ),
}


def is_supported_provider(provider_id: str) -> bool:
    return provider_id in PROVIDER_METADATA


_adapters: dict[str, AIProvider] = {}


def register_adapter(adapter: AIProvider) -> None:
    """Plug a live adapter in (Stage 18 adapters + test fakes share this)."""
    if not is_supported_provider(adapter.id):
        raise ValueError(f"cannot register adapter for unknown provider: {adapter.id!r}")
    _adapters[adapter.id] = adapter


def unregister_adapter(provider_id: str) -> None:
    """Remove an adapter (tests only — production never unregisters)."""
    _adapters.pop(provider_id, None)


def get_adapter(provider_id: str) -> AIProvider | None:
    """RAW seam: the registered fake/test double iff one exists (None unless
    `register_adapter` ran — production builtins are NOT in this map)."""
    return _adapters.get(provider_id)


def resolve_adapter(provider_id: str) -> AIProvider | None:
    """Runtime adapter resolution: registered fake first (tests shadow
    builtins by id), else the production builtin singleton, else None
    (defensive — all six providers ship builtins since Stage 18, so None
    only means a not-yet-wired future provider; callers report unavailable).

    The adapters import is LAZY (function body): adapter modules read
    `PROVIDER_METADATA` from this file, so a top-level import would cycle.
    """
    fake = _adapters.get(provider_id)
    if fake is not None:
        return fake
    from app.ai.adapters import BUILTIN_ADAPTERS

    return BUILTIN_ADAPTERS.get(provider_id)
