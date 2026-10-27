"""Provider credential endpoints (API_CONTRACT §4.6, Stage 12 — vault CRUD + test).

User-owned encrypted keys: create/list/update/rotate/delete plus a live
credential check. Covers: auth gating (401/403), creation shape + normalizers,
shape-only validation (400s), enabled/fingerprint conflicts (409s), registry
+ enabled-first list order, ownership isolation (404s), default-claim moves,
contradictory PATCHes, rotation semantics, ciphertext-at-rest proofs, the
no-adapter unavailable path, the fake-adapter test seam (ok/failed/error +
verdict recording), the dedicated test rate-limit bucket, and the vault
500s (unconfigured master key, tampered ciphertext). Plaintext keys must
NEVER appear in any response body — asserted on every journey.
"""

import hashlib
import os
import uuid
from collections.abc import Callable, Coroutine, Generator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.ai.providers import (
    AIProvider,
    AITextResult,
    ImprovementPayload,
    OverviewPayload,
    ProviderAuthResult,
    ProviderError,
    ProviderHealth,
)
from app.ai.registry import PROVIDER_IDS, register_adapter, unregister_adapter
from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.core.vault import decrypt_secret
from app.main import create_app
from app.models import User
from app.models.ai_credential import AICredential
from tests.conftest import TEST_DATABASE_URL, db_test_session, run

MASTER_KEY = Fernet.generate_key().decode("ascii")
BULLETS = "•" * 12

KEY_GROQ = "gsk_live_groq_key_for_stage12_tests_aaa1"
KEY_GROQ_2 = "gsk_live_groq_key_for_stage12_tests_bbb2"
KEY_OPENAI = "sk-test-openai-key-stage12-ccc3"
KEY_GEMINI = "AIza-test-gemini-key-stage12-ddd4"
KEY_ANTHROPIC = "sk-ant-test-anthropic-key-stage14-eee5"


@pytest.fixture(autouse=True)
def _fresh_rate_limiter() -> Generator[None, None, None]:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture(autouse=True)
def _clean_db(migrated_db: str) -> Generator[None, None, None]:
    _ = migrated_db

    async def _truncate() -> None:
        async with db_test_session():
            pass  # teardown truncates every table (see conftest)

    run(_truncate())
    yield
    run(_truncate())  # app-engine writes bypass db_test_session teardown


@pytest.fixture()
def ai_app(migrated_db: str) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage12-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    os.environ["ENCRYPTION_MASTER_KEY"] = MASTER_KEY
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def ai_client(ai_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(ai_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage12-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw(tag: str = "staple") -> str:
    return f"correct-horse-{tag}-battery-99"


async def _write(fn: Callable[[AsyncSession], Coroutine[Any, Any, Any]]) -> Any:
    """Direct-DB access WITHOUT truncation (db_test_session would wipe)."""
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            result = await fn(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


async def _verify_user(email: str) -> None:
    async def _flip(session: AsyncSession) -> None:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        user.is_verified = True

    await _write(_flip)


def _register(client: TestClient, tag: str) -> str:
    email = _email(tag)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"name": "Stage Twelve", "email": email, "password": _pw()},
        ).status_code
        == 201
    )
    return email


def _login_verified(client: TestClient, tag: str) -> str:
    email = _register(client, tag)
    run(_verify_user(email))
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": _pw()}).status_code
        == 200
    )
    return email


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def _create(
    client: TestClient, provider: str, api_key: str, label: Any = "Work key"
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/ai/providers",
        json={"provider": provider, "label": label, "api_key": api_key},
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    assert api_key not in response.text  # vault rule, every create
    return data


def _list(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/v1/ai/providers")
    assert response.status_code == 200, response.text
    data: list[dict[str, Any]] = response.json()
    return data


async def _row_by_id(credential_id: str) -> dict[str, Any]:
    """Stored columns as plain values (ORM instances detach at session close)."""

    async def _get(session: AsyncSession) -> dict[str, Any]:
        found = await session.execute(
            select(AICredential).where(AICredential.id == uuid.UUID(credential_id))
        )
        row = found.scalar_one()
        return {
            "encrypted_api_key": row.encrypted_api_key,
            "key_fingerprint": row.key_fingerprint,
            "key_version": row.key_version,
            "last4": row.last4,
            "last_test_status": row.last_test_status,
        }

    result: dict[str, Any] = await _write(_get)
    return result


class _FakeAdapter(AIProvider):
    """Test seam: proves the service hands DECRYPTED plaintext over."""

    id = "groq"
    display_name = "Groq"
    base_url = "https://api.groq.com"

    def __init__(
        self,
        *,
        expect_key: str | None,
        provider_id: str = "groq",
        display_name: str | None = None,
        health_ok: bool = True,
        auth_ok: bool = True,
        detail: str = "",
        models: tuple[str, ...] = ("fake-model-a", "fake-model-b"),
        error: ProviderError | None = None,
    ) -> None:
        self.id = provider_id
        self.display_name = display_name or provider_id.title()
        self.base_url = f"https://{provider_id}.example.com"
        self._expect_key = expect_key
        self._health_ok = health_ok
        self._auth_ok = auth_ok
        self._detail = detail
        self._models = models
        self._error = error

    async def validate_credentials(self, api_key: str) -> ProviderAuthResult:
        if self._expect_key is not None:
            assert api_key == self._expect_key
        if self._error is not None:
            raise self._error
        return ProviderAuthResult(ok=self._auth_ok, detail=self._detail)

    async def health_check(self, api_key: str) -> ProviderHealth:
        if self._expect_key is not None:
            assert api_key == self._expect_key  # decrypt→adapter proof
        if self._error is not None:
            raise self._error
        return ProviderHealth(ok=self._health_ok, detail=self._detail)

    async def list_models(self, api_key: str) -> list[str]:
        if self._expect_key is not None:
            assert api_key == self._expect_key
        return list(self._models)

    async def generate_overview(
        self, api_key: str, payload: OverviewPayload, *, timeout_s: int
    ) -> AITextResult:
        raise NotImplementedError

    async def generate_improvement(
        self, api_key: str, payload: ImprovementPayload, *, timeout_s: int
    ) -> AITextResult:
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _offline_provider_proofs() -> Generator[None, None, None]:
    """CREATE proves keys live since Stage 21; tests stay offline via fakes."""
    for provider_id in PROVIDER_IDS:
        register_adapter(_FakeAdapter(expect_key=None, provider_id=provider_id))
    try:
        yield
    finally:
        for provider_id in PROVIDER_IDS:
            unregister_adapter(provider_id)


@pytest.fixture()
def _fake_groq() -> Generator[_FakeAdapter, None, None]:
    fake = _FakeAdapter(expect_key=KEY_GROQ)
    register_adapter(fake)
    try:
        yield fake
    finally:
        unregister_adapter("groq")


class _FakeAnthropic(_FakeAdapter):
    """Same seam, Anthropic identity (proves TEST reaches any adapter)."""

    def __init__(self, *, expect_key: str) -> None:
        super().__init__(
            expect_key=expect_key,
            provider_id="anthropic",
            display_name="Anthropic",
        )


# --- auth gating ------------------------------------------------------------------


def test_anonymous_requests_are_rejected(ai_client: TestClient) -> None:
    bogus = str(uuid.uuid4())
    assert ai_client.get("/api/v1/ai/providers").status_code == 401
    assert (
        ai_client.post(
            "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ}
        ).status_code
        == 401
    )
    assert ai_client.patch(f"/api/v1/ai/providers/{bogus}", json={"label": "x"}).status_code == 401
    assert (
        ai_client.post(
            f"/api/v1/ai/providers/{bogus}/rotate-key", json={"api_key": KEY_GROQ_2}
        ).status_code
        == 401
    )
    assert ai_client.post(f"/api/v1/ai/providers/{bogus}/test").status_code == 401
    assert ai_client.delete(f"/api/v1/ai/providers/{bogus}").status_code == 401


def test_unverified_users_are_forbidden(ai_client: TestClient) -> None:
    email = _register(ai_client, "unverified")
    assert (
        ai_client.post("/api/v1/auth/login", json={"email": email, "password": _pw()}).status_code
        == 200
    )
    assert ai_client.get("/api/v1/ai/providers").status_code == 403
    response = ai_client.post(
        "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ}
    )
    assert response.status_code == 403
    assert _code(response) == "email_unverified"


# --- creation ---------------------------------------------------------------------


def test_create_returns_safe_metadata_shape(ai_client: TestClient) -> None:
    _login_verified(ai_client, "create")
    data = _create(ai_client, "groq", KEY_GROQ)
    assert set(data) == {
        "id",
        "provider",
        "label",
        "masked_key",
        "is_enabled",
        "is_default",
        "fallback_rank",
        "key_version",
        "last_tested_at",
        "last_test_status",
    }
    assert data["provider"] == "groq"
    assert data["label"] == "Work key"
    assert data["masked_key"] == f"{BULLETS}{KEY_GROQ[-4:]}"
    assert data["is_enabled"] is True
    assert data["is_default"] is False  # creation never claims default
    assert data["fallback_rank"] == 0
    assert data["key_version"] == 1
    assert data["last_tested_at"] is not None
    assert data["last_test_status"] == "ok"


def test_create_normalizes_label(ai_client: TestClient) -> None:
    _login_verified(ai_client, "label")
    assert _create(ai_client, "groq", KEY_GROQ, label="  Work  ")["label"] == "Work"
    assert _create(ai_client, "openai", KEY_OPENAI, label="   ")["label"] is None
    assert _create(ai_client, "gemini", KEY_GEMINI, label=None)["label"] is None


def test_create_rejects_unknown_provider(ai_client: TestClient) -> None:
    _login_verified(ai_client, "unknown")
    response = ai_client.post(
        "/api/v1/ai/providers", json={"provider": "skynet", "api_key": KEY_GROQ}
    )
    assert response.status_code == 400
    assert _code(response) == "validation_error"


def test_create_rejects_short_and_huge_keys(ai_client: TestClient) -> None:
    _login_verified(ai_client, "keyshape")
    short = ai_client.post("/api/v1/ai/providers", json={"provider": "groq", "api_key": "abc"})
    assert short.status_code == 400
    assert _code(short) == "validation_error"
    huge = ai_client.post("/api/v1/ai/providers", json={"provider": "groq", "api_key": "k" * 2001})
    assert huge.status_code == 400
    long_label = ai_client.post(
        "/api/v1/ai/providers",
        json={"provider": "groq", "label": "l" * 81, "api_key": KEY_GROQ},
    )
    assert long_label.status_code == 400


def test_create_proves_key_before_storage(ai_client: TestClient) -> None:
    fake = _FakeAdapter(expect_key=KEY_GROQ, auth_ok=False, detail="Key rejected by provider.")
    register_adapter(fake)
    _login_verified(ai_client, "proofbad")
    response = ai_client.post(
        "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ}
    )
    assert response.status_code == 400
    assert _code(response) == "validation_error"
    assert "Key rejected" in response.json()["error"]["message"]
    assert _list(ai_client) == []


def test_create_provider_error_stores_nothing(ai_client: TestClient) -> None:
    fake = _FakeAdapter(
        expect_key=KEY_GROQ,
        error=ProviderError("auth", "Groq rejected the API key. Check the key in Settings."),
    )
    register_adapter(fake)
    _login_verified(ai_client, "prooferr")
    response = ai_client.post(
        "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ}
    )
    assert response.status_code == 400
    assert _code(response) == "validation_error"
    assert "rejected" in response.json()["error"]["message"]
    assert _list(ai_client) == []


def test_create_rejects_duplicate_enabled_provider(ai_client: TestClient) -> None:
    _login_verified(ai_client, "dup")
    _create(ai_client, "groq", KEY_GROQ)
    response = ai_client.post(
        "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ_2}
    )
    assert response.status_code == 409
    assert _code(response) == "conflict"


def test_create_rejects_known_key_even_when_disabled(ai_client: TestClient) -> None:
    _login_verified(ai_client, "dupkey")
    row = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_enabled": False}).status_code
        == 200
    )
    response = ai_client.post(
        "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ}
    )
    assert response.status_code == 409
    assert "rotat" in response.json()["error"]["message"]


def test_same_key_is_allowed_on_another_provider(ai_client: TestClient) -> None:
    _login_verified(ai_client, "crossprov")
    _create(ai_client, "groq", KEY_GROQ)
    data = _create(ai_client, "openai", KEY_GROQ)  # fingerprints are per-provider
    assert data["provider"] == "openai"


def test_ciphertext_at_rest_decrypts_to_key(ai_client: TestClient) -> None:
    _login_verified(ai_client, "atrest")
    data = _create(ai_client, "groq", KEY_GROQ)
    row = run(_row_by_id(data["id"]))
    assert str(row["encrypted_api_key"]).startswith("v1:")
    assert KEY_GROQ not in str(row["encrypted_api_key"])
    assert decrypt_secret(str(row["encrypted_api_key"])) == KEY_GROQ
    assert row["key_fingerprint"] == hashlib.sha256(KEY_GROQ.encode()).hexdigest()[:16]
    assert row["last4"] == KEY_GROQ[-4:]
    assert row["key_version"] == 1


# --- listing ----------------------------------------------------------------------


def test_list_is_empty_array_for_new_accounts(ai_client: TestClient) -> None:
    _login_verified(ai_client, "empty")
    assert _list(ai_client) == []


def test_list_follows_registry_order(ai_client: TestClient) -> None:
    _login_verified(ai_client, "order")
    _create(ai_client, "openai", KEY_OPENAI)
    _create(ai_client, "gemini", KEY_GEMINI)
    _create(ai_client, "groq", KEY_GROQ)
    assert [row["provider"] for row in _list(ai_client)] == ["gemini", "groq", "openai"]


def test_list_prefers_enabled_within_a_provider(ai_client: TestClient) -> None:
    _login_verified(ai_client, "enabledfirst")
    first = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{first['id']}", json={"is_enabled": False}
        ).status_code
        == 200
    )
    second = _create(ai_client, "groq", KEY_GROQ_2)
    rows = _list(ai_client)
    assert [row["id"] for row in rows] == [second["id"], first["id"]]
    assert [row["is_enabled"] for row in rows] == [True, False]


def test_list_never_leaks_foreign_rows(ai_client: TestClient) -> None:
    _login_verified(ai_client, "owner")
    owned = _create(ai_client, "groq", KEY_GROQ)
    ai_client.cookies.clear()  # same client, new identity (nested TestClients fight over loops)
    _login_verified(ai_client, "stranger")
    assert _list(ai_client) == []
    bogus_patch = ai_client.patch(f"/api/v1/ai/providers/{owned['id']}", json={"label": "x"})
    assert bogus_patch.status_code == 404
    assert _code(bogus_patch) == "ai_provider_not_found"
    assert ai_client.delete(f"/api/v1/ai/providers/{owned['id']}").status_code == 404
    assert ai_client.post(f"/api/v1/ai/providers/{owned['id']}/test").status_code == 404


# --- updates ----------------------------------------------------------------------


def test_update_edits_label_and_rank(ai_client: TestClient) -> None:
    _login_verified(ai_client, "edit")
    row = _create(ai_client, "groq", KEY_GROQ)
    response = ai_client.patch(
        f"/api/v1/ai/providers/{row['id']}", json={"label": "Prod", "fallback_rank": 7}
    )
    assert response.status_code == 200, response.text
    assert response.json()["label"] == "Prod"
    assert response.json()["fallback_rank"] == 7
    cleared = ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"label": None})
    assert cleared.json()["label"] is None
    untouched = ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"fallback_rank": 9})
    assert untouched.json()["label"] is None  # absent leaves alone


def test_update_rejects_bad_rank(ai_client: TestClient) -> None:
    _login_verified(ai_client, "rank")
    row = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"fallback_rank": -1}).status_code
        == 400
    )
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{row['id']}", json={"fallback_rank": 32768}
        ).status_code
        == 400
    )


def test_default_claim_moves_the_single_default(ai_client: TestClient) -> None:
    _login_verified(ai_client, "default")
    first = _create(ai_client, "groq", KEY_GROQ)
    second = _create(ai_client, "openai", KEY_OPENAI)
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{first['id']}", json={"is_default": True}
        ).status_code
        == 200
    )
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{second['id']}", json={"is_default": True}
        ).status_code
        == 200
    )
    rows = _list(ai_client)
    assert [row["is_default"] for row in rows].count(True) == 1
    assert [row for row in rows if row["is_default"]][0]["id"] == second["id"]
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{second['id']}", json={"is_default": False}
        ).status_code
        == 200
    )
    assert all(not row["is_default"] for row in _list(ai_client))


def test_update_rejects_contradictory_default_while_disabled(ai_client: TestClient) -> None:
    _login_verified(ai_client, "contradict")
    row = _create(ai_client, "groq", KEY_GROQ)
    response = ai_client.patch(
        f"/api/v1/ai/providers/{row['id']}", json={"is_enabled": False, "is_default": True}
    )
    assert response.status_code == 409
    assert _code(response) == "conflict"
    # Defaulting an already-disabled row is the same contradiction.
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_enabled": False}).status_code
        == 200
    )
    response = ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_default": True})
    assert response.status_code == 409


def test_disabling_the_default_auto_clears_it(ai_client: TestClient) -> None:
    _login_verified(ai_client, "autoclear")
    row = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_default": True}).status_code
        == 200
    )
    response = ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_enabled": False})
    assert response.status_code == 200, response.text
    assert response.json()["is_enabled"] is False
    assert response.json()["is_default"] is False


def test_reenabling_into_an_occupied_provider_conflicts(ai_client: TestClient) -> None:
    _login_verified(ai_client, "reoccupy")
    first = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{first['id']}", json={"is_enabled": False}
        ).status_code
        == 200
    )
    _create(ai_client, "groq", KEY_GROQ_2)
    response = ai_client.patch(f"/api/v1/ai/providers/{first['id']}", json={"is_enabled": True})
    assert response.status_code == 409
    assert _code(response) == "conflict"


def test_update_unknown_and_malformed_ids(ai_client: TestClient) -> None:
    _login_verified(ai_client, "patch404")
    missing = ai_client.patch(f"/api/v1/ai/providers/{uuid.uuid4()}", json={"label": "x"})
    assert missing.status_code == 404
    assert _code(missing) == "ai_provider_not_found"
    malformed = ai_client.patch("/api/v1/ai/providers/not-a-uuid", json={"label": "x"})
    assert malformed.status_code == 400  # wire truth: malformed UUIDs are 400
    assert _code(malformed) == "validation_error"


# --- rotation ---------------------------------------------------------------------


def test_rotate_replaces_key_and_clears_verdict(
    ai_client: TestClient, _fake_groq: _FakeAdapter
) -> None:
    _ = _fake_groq
    _login_verified(ai_client, "rotate")
    row = _create(ai_client, "groq", KEY_GROQ)
    before = run(_row_by_id(row["id"]))
    assert ai_client.post(f"/api/v1/ai/providers/{row['id']}/test").status_code == 200
    assert run(_row_by_id(row["id"]))["last_test_status"] == "ok"
    response = ai_client.post(
        f"/api/v1/ai/providers/{row['id']}/rotate-key", json={"api_key": KEY_GROQ_2}
    )
    assert response.status_code == 200, response.text
    assert KEY_GROQ_2 not in response.text
    assert response.json()["masked_key"] == f"{BULLETS}{KEY_GROQ_2[-4:]}"
    assert response.json()["last_tested_at"] is None
    assert response.json()["last_test_status"] is None
    after = run(_row_by_id(row["id"]))
    assert after["encrypted_api_key"] != before["encrypted_api_key"]
    assert decrypt_secret(str(after["encrypted_api_key"])) == KEY_GROQ_2


def test_rotate_rejects_short_keys(ai_client: TestClient) -> None:
    _login_verified(ai_client, "rotshape")
    row = _create(ai_client, "groq", KEY_GROQ)
    response = ai_client.post(
        f"/api/v1/ai/providers/{row['id']}/rotate-key", json={"api_key": "abc"}
    )
    assert response.status_code == 400
    assert _code(response) == "validation_error"


def test_rotate_accepts_resaving_the_current_key(ai_client: TestClient) -> None:
    _login_verified(ai_client, "rotsame")
    row = _create(ai_client, "groq", KEY_GROQ)
    response = ai_client.post(
        f"/api/v1/ai/providers/{row['id']}/rotate-key", json={"api_key": KEY_GROQ}
    )
    assert response.status_code == 200, response.text


def test_rotate_rejects_key_living_on_another_row(ai_client: TestClient) -> None:
    _login_verified(ai_client, "rotconflict")
    first = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{first['id']}", json={"is_enabled": False}
        ).status_code
        == 200
    )
    second = _create(ai_client, "groq", KEY_GROQ_2)
    response = ai_client.post(
        f"/api/v1/ai/providers/{second['id']}/rotate-key", json={"api_key": KEY_GROQ}
    )
    assert response.status_code == 409
    assert _code(response) == "conflict"


# --- deletion ---------------------------------------------------------------------


def test_delete_removes_the_row(ai_client: TestClient) -> None:
    _login_verified(ai_client, "delete")
    row = _create(ai_client, "groq", KEY_GROQ)
    assert ai_client.delete(f"/api/v1/ai/providers/{row['id']}").status_code == 204
    assert ai_client.delete(f"/api/v1/ai/providers/{row['id']}").status_code == 404
    assert _list(ai_client) == []

    async def _missing(session: AsyncSession) -> None:
        found = await session.execute(
            select(AICredential).where(AICredential.id == uuid.UUID(row["id"]))
        )
        assert found.scalar_one_or_none() is None

    run(_write(_missing))


def test_deleting_the_default_leaves_no_default(ai_client: TestClient) -> None:
    _login_verified(ai_client, "deldefault")
    row = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_default": True}).status_code
        == 200
    )
    assert ai_client.delete(f"/api/v1/ai/providers/{row['id']}").status_code == 204
    assert _list(ai_client) == []


# --- credential test --------------------------------------------------------------


def test_missing_adapter_reports_unavailable(
    ai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Defensive branch pin: all six ship adapters, so force the None path
    # (a not-yet-wired future provider) — TEST stays deterministically
    # unavailable without touching the vault plaintext or the verdict.
    import app.services.ai_providers as provider_service

    _login_verified(ai_client, "unavail")
    row = _create(ai_client, "groq", KEY_GROQ)
    monkeypatch.setattr(provider_service, "resolve_adapter", lambda provider_id: None)
    response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["models"] == []
    assert body["latency_ms"] == 0
    assert "not available yet" in (body["error"] or "")
    assert KEY_GROQ not in response.text
    listed = _list(ai_client)[0]  # no TEST attempt ran: create-proof verdict stays untouched
    assert listed["last_tested_at"] is not None
    assert listed["last_test_status"] == "ok"


def test_anthropic_test_reaches_its_adapter(ai_client: TestClient) -> None:
    # Stage 18 re-entry proof: anthropic resolves an adapter now, so TEST
    # exercises the adapter path (decrypt → health → verdict), never the
    # unavailable short-circuit.
    fake = _FakeAnthropic(expect_key=KEY_ANTHROPIC)
    register_adapter(fake)
    try:
        _login_verified(ai_client, "anthtest")
        row = _create(ai_client, "anthropic", KEY_ANTHROPIC)
        response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
    finally:
        unregister_adapter("anthropic")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["models"] == ["fake-model-a", "fake-model-b"]
    assert body["error"] is None
    assert KEY_ANTHROPIC not in response.text
    listed = _list(ai_client)[0]
    assert listed["last_tested_at"] is not None
    assert listed["last_test_status"] == "ok"


def test_with_fake_adapter_records_success(ai_client: TestClient, _fake_groq: _FakeAdapter) -> None:
    _ = _fake_groq
    _login_verified(ai_client, "testok")
    row = _create(ai_client, "groq", KEY_GROQ)
    response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["models"] == ["fake-model-a", "fake-model-b"]
    assert body["latency_ms"] >= 0
    assert body["error"] is None
    assert KEY_GROQ not in response.text
    listed = _list(ai_client)[0]
    assert listed["last_tested_at"] is not None
    assert listed["last_test_status"] == "ok"


def test_failed_health_records_failure(ai_client: TestClient) -> None:
    fake = _FakeAdapter(expect_key=KEY_GROQ, health_ok=False, detail="Key rejected by provider.")
    register_adapter(fake)
    try:
        _login_verified(ai_client, "testfail")
        row = _create(ai_client, "groq", KEY_GROQ)
        response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is False
        assert body["error"] == "Key rejected by provider."
        assert _list(ai_client)[0]["last_test_status"] == "failed"
    finally:
        unregister_adapter("groq")


def test_provider_error_surfaces_user_message_only(ai_client: TestClient) -> None:
    _login_verified(ai_client, "testerr")
    row = _create(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter(
        expect_key=KEY_GROQ,
        error=ProviderError("auth", "Invalid API key."),
    )
    register_adapter(fake)
    try:
        response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is False
        assert body["error"] == "Invalid API key."
        assert body["models"] == []
        assert _list(ai_client)[0]["last_test_status"] == "failed"
    finally:
        unregister_adapter("groq")


def test_disabled_credentials_still_test(ai_client: TestClient, _fake_groq: _FakeAdapter) -> None:
    _ = _fake_groq
    _login_verified(ai_client, "testdisabled")
    row = _create(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_enabled": False}).status_code
        == 200
    )
    response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True


def test_unknown_credential_tests_404(ai_client: TestClient) -> None:
    _login_verified(ai_client, "test404")
    response = ai_client.post(f"/api/v1/ai/providers/{uuid.uuid4()}/test")
    assert response.status_code == 404
    assert _code(response) == "ai_provider_not_found"


def test_test_bucket_rate_limits(ai_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login_verified(ai_client, "testrl")
    row = _create(ai_client, "groq", KEY_GROQ)
    monkeypatch.setenv("RATE_LIMIT_AI_TEST_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        assert ai_client.post(f"/api/v1/ai/providers/{row['id']}/test").status_code == 200
        assert ai_client.post(f"/api/v1/ai/providers/{row['id']}/test").status_code == 200
        limited = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
        assert limited.status_code == 429
        assert _code(limited) == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1
    finally:
        get_settings.cache_clear()


# --- vault failures -----------------------------------------------------------------


def test_unconfigured_vault_fails_creates_with_500(
    ai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_verified(ai_client, "novault")
    monkeypatch.delenv("ENCRYPTION_MASTER_KEY", raising=False)
    get_settings.cache_clear()
    try:
        response = ai_client.post(
            "/api/v1/ai/providers", json={"provider": "groq", "api_key": KEY_GROQ}
        )
        assert response.status_code == 500
        assert _code(response) == "internal_error"
        assert KEY_GROQ not in response.text
    finally:
        get_settings.cache_clear()


def test_tampered_ciphertext_fails_tests_with_500(
    ai_client: TestClient, _fake_groq: _FakeAdapter
) -> None:
    _ = _fake_groq
    _login_verified(ai_client, "tampered")
    row = _create(ai_client, "groq", KEY_GROQ)

    async def _tamper(session: AsyncSession) -> None:
        stored = (
            await session.execute(
                select(AICredential).where(AICredential.id == uuid.UUID(row["id"]))
            )
        ).scalar_one()
        stored.encrypted_api_key = "v1:this-is-not-a-valid-token"

    run(_write(_tamper))
    response = ai_client.post(f"/api/v1/ai/providers/{row['id']}/test")
    assert response.status_code == 500
    assert _code(response) == "internal_error"
