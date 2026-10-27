"""AI provider credential schemas (API_CONTRACT §4.6 — Stage 12 vault CRUD).

Plaintext keys appear ONLY in inbound `POST`/`rotate-key` bodies (opaque,
edge-trimmed, length-bounded); responses are allowlist-serialized metadata —
`masked_key` carries the last 4 chars behind bullets and NOTHING else
identifies the key. Unknown provider ids fail as `400 validation_error`
(the project's Literal-vocabulary convention, like band/sort/range).
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

ProviderId = Literal["gemini", "groq", "openai", "anthropic", "openrouter", "huggingface"]

# Opaque user key: edge whitespace is never significant (paste artifacts are
# trimmed), ≥4 chars fills `last4` honestly, ≤2000 bounds abuse.
ApiKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2000)]


class ProviderCreateRequest(BaseModel):
    """Store a credential: always enabled, never default (explicit PATCH opts
    into default). Stage 21 proves the key live before encrypted storage."""

    provider: ProviderId
    label: str | None = Field(default=None, max_length=80)
    api_key: ApiKey


class ProviderUpdateRequest(BaseModel):
    """Metadata update (key rotation has its own endpoint). All-None bodies
    are a no-op returning current metadata. `{is_enabled: false, is_default:
    true}` is contradictory → `409 conflict`; disabling the default
    auto-clears `is_default` in the same transaction."""

    label: str | None = Field(default=None, max_length=80)
    is_enabled: bool | None = None
    is_default: bool | None = None
    fallback_rank: int | None = Field(default=None, ge=0, le=32767)


class RotateKeyRequest(BaseModel):
    """Replace the stored key (new ciphertext + fingerprint; any previous
    test verdict is cleared — the new key is unproven)."""

    api_key: ApiKey


class ProviderMetadataResponse(BaseModel):
    """Safe credential metadata — the ONLY shape that ever leaves the vault."""

    id: UUID
    provider: ProviderId
    label: str | None = None
    masked_key: str
    is_enabled: bool
    is_default: bool
    fallback_rank: int
    key_version: int
    last_tested_at: datetime | None = None
    last_test_status: Literal["ok", "failed"] | None = None


class ProviderTestResponse(BaseModel):
    """Credential-test verdict (always 200: the TEST failed, not the request).
    `error` is user-safe adapter text; `models`/`latency_ms` describe a
    completed attempt (empty/zero when no attempt ran)."""

    ok: bool
    models: list[str] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    error: str | None = None
