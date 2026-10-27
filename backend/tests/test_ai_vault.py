"""Vault + provider-registry unit tests (Stage 12 — no database needed).

The vault is the trust root for every stored key, so these tests pin its
failure semantics exactly: roundtrip, non-determinism, wrong-key / tampered /
malformed ciphertext, missing-vs-malformed master key, fingerprint shape, and
the hard rule that NO failure mode ever echoes secret material. Registry
tests pin the six-provider table, order, the fake-only raw seam, and
`resolve_adapter` (one builtin per provider — fakes shadow builtins
by id, unknown ids miss).
"""

from collections.abc import Generator

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError as PydanticValidationError

from app.ai.providers import (
    AIProvider,
    AITextResult,
    ImprovementPayload,
    OverviewPayload,
    ProviderAuthResult,
    ProviderHealth,
)
from app.ai.registry import (
    PROVIDER_IDS,
    PROVIDER_METADATA,
    PROVIDER_ORDER,
    get_adapter,
    is_supported_provider,
    register_adapter,
    resolve_adapter,
    unregister_adapter,
)
from app.core.config import get_settings
from app.core.vault import (
    VAULT_VERSION,
    VaultError,
    decrypt_secret,
    encrypt_secret,
    fingerprint_secret,
)

MASTER_KEY = Fernet.generate_key().decode("ascii")
OTHER_KEY = Fernet.generate_key().decode("ascii")
SAMPLE_KEY = "groq-live-key-abcdef-12345678"


@pytest.fixture(autouse=True)
def _vault_key(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", MASTER_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- vault roundtrip ------------------------------------------------------------


def test_encrypt_returns_versioned_ciphertext() -> None:
    ciphertext, version = encrypt_secret(SAMPLE_KEY)
    assert version == VAULT_VERSION == 1
    assert ciphertext.startswith("v1:")
    assert SAMPLE_KEY not in ciphertext


def test_decrypt_roundtrip() -> None:
    ciphertext, _ = encrypt_secret(SAMPLE_KEY)
    assert decrypt_secret(ciphertext) == SAMPLE_KEY


def test_encrypt_is_nondeterministic() -> None:
    first, _ = encrypt_secret(SAMPLE_KEY)
    second, _ = encrypt_secret(SAMPLE_KEY)
    assert first != second  # Fernet IVs differ…
    assert decrypt_secret(first) == decrypt_secret(second) == SAMPLE_KEY


def test_decrypt_rejects_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    ciphertext, _ = encrypt_secret(SAMPLE_KEY)
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", OTHER_KEY)
    get_settings.cache_clear()
    try:
        with pytest.raises(VaultError):
            decrypt_secret(ciphertext)
    finally:
        get_settings.cache_clear()


def test_decrypt_rejects_tampered_token() -> None:
    ciphertext, _ = encrypt_secret(SAMPLE_KEY)
    head, token = ciphertext.split(":", 1)
    tampered = f"{head}:{token[:-2]}{'AA' if not token.endswith('AA') else 'BB'}"
    assert tampered != ciphertext
    with pytest.raises(VaultError):
        decrypt_secret(tampered)


@pytest.mark.parametrize(
    "ciphertext",
    ["", "v1:", "v9:some-token", "vX:token", "no-prefix-at-all", "1:token", "v:token"],
    ids=["empty", "empty-token", "unknown-version", "non-numeric", "no-prefix", "bare", "bare-v"],
)
def test_decrypt_rejects_malformed_ciphertext(ciphertext: str) -> None:
    with pytest.raises(VaultError):
        decrypt_secret(ciphertext)


def test_vault_errors_never_echo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    ciphertext, _ = encrypt_secret(SAMPLE_KEY)
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", OTHER_KEY)
    get_settings.cache_clear()
    try:
        with pytest.raises(VaultError) as exc_info:
            decrypt_secret(ciphertext)
    finally:
        get_settings.cache_clear()
    message = str(exc_info.value)
    assert SAMPLE_KEY not in message
    assert MASTER_KEY not in message and OTHER_KEY not in message
    assert ciphertext not in message


def test_missing_master_key_fails_at_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_MASTER_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().ENCRYPTION_MASTER_KEY is None  # absent is legal…
        with pytest.raises(VaultError, match="not configured"):
            encrypt_secret(SAMPLE_KEY)
        with pytest.raises(VaultError, match="not configured"):
            decrypt_secret("v1:whatever")
    finally:
        get_settings.cache_clear()


def test_malformed_master_key_fails_closed_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", "not-a-fernet-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(PydanticValidationError, match="ENCRYPTION_MASTER_KEY"):
            get_settings()
    finally:
        get_settings.cache_clear()


# --- fingerprints ---------------------------------------------------------------


def test_fingerprint_is_stable_short_hex() -> None:
    first = fingerprint_secret(SAMPLE_KEY)
    assert first == fingerprint_secret(SAMPLE_KEY)
    assert len(first) == 16
    int(first, 16)  # hex charset
    assert SAMPLE_KEY not in first


def test_fingerprint_distinguishes_keys() -> None:
    assert fingerprint_secret(SAMPLE_KEY) != fingerprint_secret(SAMPLE_KEY + "-other")


# --- registry -------------------------------------------------------------------


def test_registry_lists_six_providers_in_contract_order() -> None:
    assert PROVIDER_IDS == ("gemini", "groq", "openai", "anthropic", "openrouter", "huggingface")
    assert sorted(PROVIDER_ORDER, key=PROVIDER_ORDER.__getitem__) == list(PROVIDER_IDS)
    assert set(PROVIDER_METADATA) == set(PROVIDER_IDS)


def test_registry_metadata_is_public_and_https() -> None:
    for provider_id in PROVIDER_IDS:
        meta = PROVIDER_METADATA[provider_id]
        assert meta.id == provider_id
        assert meta.display_name.strip()
        assert meta.base_url.startswith("https://")
        assert is_supported_provider(provider_id)
    assert not is_supported_provider("openal")


def test_raw_adapter_seam_holds_fakes_only() -> None:
    # Stage 14: `get_adapter` is the fake-only seam (builtins resolve via
    # `resolve_adapter`, never here) — nothing registers builtins globally,
    # so suites stay hermetic whatever ran before.
    saved = {provider_id: get_adapter(provider_id) for provider_id in PROVIDER_IDS}
    for provider_id in PROVIDER_IDS:
        unregister_adapter(provider_id)
    try:
        for provider_id in PROVIDER_IDS:
            assert get_adapter(provider_id) is None
    finally:
        for fake in saved.values():
            if fake is not None:
                register_adapter(fake)


def test_resolve_adapter_serves_all_six_builtins() -> None:
    saved = {provider_id: get_adapter(provider_id) for provider_id in PROVIDER_IDS}
    for provider_id in PROVIDER_IDS:
        unregister_adapter(provider_id)
    try:
        for provider_id in PROVIDER_IDS:
            adapter = resolve_adapter(provider_id)
            assert adapter is not None
            assert adapter.id == provider_id
        assert resolve_adapter("skynet") is None  # unknown ids still miss
    finally:
        for fake in saved.values():
            if fake is not None:
                register_adapter(fake)


def test_resolve_adapter_prefers_registered_fake() -> None:
    fake = _FakeAdapter()
    try:
        register_adapter(fake)
        assert resolve_adapter("groq") is fake  # tests shadow builtins by id
    finally:
        unregister_adapter("groq")


class _FakeAdapter(AIProvider):
    id = "groq"
    display_name = "Groq"
    base_url = "https://api.groq.com"

    async def validate_credentials(self, api_key: str) -> ProviderAuthResult:
        _ = api_key
        return ProviderAuthResult(ok=True)

    async def health_check(self, api_key: str) -> ProviderHealth:
        _ = api_key
        return ProviderHealth(ok=True)

    async def list_models(self, api_key: str) -> list[str]:
        _ = api_key
        return ["fake-model"]

    async def generate_overview(
        self, api_key: str, payload: OverviewPayload, *, timeout_s: int
    ) -> AITextResult:
        raise NotImplementedError

    async def generate_improvement(
        self, api_key: str, payload: ImprovementPayload, *, timeout_s: int
    ) -> AITextResult:
        raise NotImplementedError


def test_adapter_seam_registers_and_unregisters() -> None:
    fake = _FakeAdapter()
    try:
        register_adapter(fake)
        assert get_adapter("groq") is fake
    finally:
        unregister_adapter("groq")
    assert get_adapter("groq") is None


def test_adapter_seam_rejects_unknown_provider() -> None:
    fake = _FakeAdapter()
    fake.id = "skynet"
    with pytest.raises(ValueError, match="unknown provider"):
        register_adapter(fake)
    assert get_adapter("skynet") is None
