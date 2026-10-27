"""AI enhancement wiring (Stage 14 — fake adapters, real database, no network).

The deterministic pipeline stays authoritative: every test asserts the
201 + intact scores/issues FIRST, then the AI outcome. Covers: `skipped`
(false = deterministic-only, providers untouched), `unconfigured` (none /
disabled credentials), `ok` (overview + rewrites persisted, originals
immutable, GET-after identical), `failed` fail-open (first error wins,
deterministic intact), the default→fallback chain, adapterless-credential
guidance, per-requirement best-effort, crash/vault fail-open, the
improvement count cap, the `ai_error` 300-char cap, and the document-upload
`ai_enhance` field. Plaintext keys must NEVER appear in any response body.
"""

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
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
from app.ai.registry import register_adapter, unregister_adapter
from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.main import create_app
from app.models import User
from tests.conftest import TEST_DATABASE_URL, db_test_session, run

MASTER_KEY = Fernet.generate_key().decode("ascii")

KEY_GROQ = "gsk_live_groq_key_for_stage14_tests_aaa1"
KEY_OPENAI = "sk-test-openai-key-stage14-bbb2"
KEY_ANTHROPIC = "sk-ant-test-anthropic-key-stage14-ccc3"

SAMPLE_SRS = (
    "# Functional Requirements\n\n"
    "FR-001: The system shall allow login with email quickly.\n\n"
    "1. The admin must promptly approve new accounts.\n"
    "- The audit log shall record every login attempt.\n\n"
    "The dashboard should load fast for all users.\n"
)


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
    os.environ["JWT_SECRET"] = "stage14-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    os.environ["ENCRYPTION_MASTER_KEY"] = MASTER_KEY
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def ai_client(ai_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(ai_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage14-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw() -> str:
    return "correct-horse-stage14-battery-99"


async def _write(fn: Any) -> Any:
    """Direct-DB access on a FRESH engine (the app engine belongs to the
    TestClient portal loop — touching it here trips the single-loop rule)."""
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


def _login_verified(client: TestClient, tag: str) -> None:
    email = _email(tag)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"name": "Stage Fourteen", "email": email, "password": _pw()},
        ).status_code
        == 201
    )
    run(_verify_user(email))
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": _pw()}).status_code
        == 200
    )


def _create_credential(client: TestClient, provider: str, api_key: str) -> dict[str, Any]:
    # Stage 21: CREATE proves keys through the adapter, so tests register an
    # offline fake for the proof call. Scenario-specific fakes still wrap the
    # later enhancement calls.
    with _adapters(_FakeAdapter(provider)):
        response = client.post(
            "/api/v1/ai/providers", json={"provider": provider, "api_key": api_key}
        )
    assert response.status_code == 201, response.text
    assert api_key not in response.text
    return dict(response.json())


def _analyze(client: TestClient, ai_enhance: bool, text: str = SAMPLE_SRS) -> Any:
    return client.post(
        "/api/v1/analysis",
        json={"title": "AI test", "text": text, "options": {"ai_enhance": ai_enhance}},
    )


class _FakeAdapter(AIProvider):
    """Scripted generation fake: `overview`/`improvement` are either text, a
    `ProviderError` to raise, an unexpected exception to raise, or (for
    improvements) a callable over the requirement text. `seen` records every
    call for chain-ordering assertions."""

    def __init__(
        self,
        provider_id: str,
        *,
        overview: Any = "Fake overview.",
        improvement: Any = "Fake rewrite.",
        expect_key: str | None = None,
        seen: list[str] | None = None,
    ) -> None:
        self.id = provider_id
        self.display_name = provider_id.title()
        self.base_url = f"https://{provider_id}.example.com"
        self._overview = overview
        self._improvement = improvement
        self._expect_key = expect_key
        self._seen = seen if seen is not None else []

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
        _ = (payload, timeout_s)
        self._check(api_key)
        self._seen.append(f"{self.id}:overview")
        if isinstance(self._overview, Exception):
            raise self._overview
        return AITextResult(text=str(self._overview), model="fake-model", latency_ms=1)

    async def generate_improvement(
        self, api_key: str, payload: ImprovementPayload, *, timeout_s: int
    ) -> AITextResult:
        _ = timeout_s
        self._check(api_key)
        self._seen.append(f"{self.id}:improvement")
        behavior = self._improvement
        if callable(behavior):
            behavior = behavior(payload.requirement_text)
        if isinstance(behavior, Exception):
            raise behavior
        return AITextResult(text=str(behavior), model="fake-model", latency_ms=1)

    def _check(self, api_key: str) -> None:
        if self._expect_key is not None:
            assert api_key == self._expect_key  # vault handed the RIGHT key over


@contextmanager
def _adapters(*fakes: _FakeAdapter) -> Generator[None, None, None]:
    for fake in fakes:
        register_adapter(fake)
    try:
        yield
    finally:
        for fake in fakes:
            unregister_adapter(fake.id)


# --- skipped / unconfigured --------------------------------------------------


def test_ai_enhance_false_skips_without_touching_providers(ai_client: TestClient) -> None:
    _login_verified(ai_client, "skip")
    _create_credential(ai_client, "groq", KEY_GROQ)
    seen: list[str] = []
    fake = _FakeAdapter("groq", expect_key=KEY_GROQ, seen=seen)
    with _adapters(fake):
        response = _analyze(ai_client, False)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["ai_status"] == "skipped"
    assert body["ai_overview"] is None and body["ai_provider"] is None
    assert body["ai_error"] is None
    assert all(item["suggested_rewrite"] is None for item in body["requirements"])
    assert seen == []  # providers untouched when ai_enhance is false


def test_ai_enhance_true_without_credentials_is_unconfigured(ai_client: TestClient) -> None:
    _login_verified(ai_client, "unconf")
    response = _analyze(ai_client, True)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["issues_count"] > 0  # deterministic findings intact
    assert body["ai_status"] == "unconfigured"
    assert body["ai_overview"] is None and body["ai_error"] is None  # not an error: no text
    detail = ai_client.get(f"/api/v1/analysis/{body['id']}").json()
    assert detail["ai_status"] == "unconfigured"  # persisted, GET-after identical


def test_disabled_only_credentials_are_unconfigured(ai_client: TestClient) -> None:
    _login_verified(ai_client, "disabled")
    row = _create_credential(ai_client, "groq", KEY_GROQ)
    assert (
        ai_client.patch(f"/api/v1/ai/providers/{row['id']}", json={"is_enabled": False}).status_code
        == 200
    )
    body = _analyze(ai_client, True).json()
    assert body["status"] == "analyzed"
    assert body["ai_status"] == "unconfigured"


# --- ok ----------------------------------------------------------------------


def test_success_persists_overview_and_rewrites(ai_client: TestClient) -> None:
    _login_verified(ai_client, "ok")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter("groq", overview="OVERVIEW.", improvement="REWRITE.", expect_key=KEY_GROQ)
    with _adapters(fake):
        response = _analyze(ai_client, True)
    assert response.status_code == 201, response.text
    assert KEY_GROQ not in response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["ai_status"] == "ok"
    assert body["ai_provider"] == "groq"
    assert body["ai_overview"] == "OVERVIEW."
    assert body["ai_error"] is None
    first = body["requirements"][0]
    assert first["suggested_rewrite"] == "REWRITE."
    assert first["suggestion_source"] == "ai"
    assert "quickly" in first["text"]  # original immutable — rewrite is additive
    detail = ai_client.get(f"/api/v1/analysis/{body['id']}").json()
    assert detail["ai_overview"] == "OVERVIEW."  # persisted, GET-after identical
    assert detail["requirements"][0]["suggested_rewrite"] == "REWRITE."
    assert detail["requirements"][0]["suggestion_source"] == "ai"


def test_clean_requirements_get_no_rewrite(ai_client: TestClient) -> None:
    _login_verified(ai_client, "clean")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter("groq", expect_key=KEY_GROQ)
    text = "FR-001: The system shall allow login with email.\n"
    with _adapters(fake):
        body = _analyze(ai_client, True, text=text).json()
    assert body["ai_status"] == "ok"
    assert body["requirements"][0]["issues"] == []
    assert body["requirements"][0]["suggested_rewrite"] is None  # nothing to fix


def test_improvements_capped_per_run(ai_client: TestClient) -> None:
    _login_verified(ai_client, "cap")
    _create_credential(ai_client, "groq", KEY_GROQ)
    text = "".join(f"{n}. The system shall respond quickly to input {n}.\n" for n in range(1, 16))
    fake = _FakeAdapter("groq", expect_key=KEY_GROQ)
    with _adapters(fake):
        body = _analyze(ai_client, True, text=text).json()
    assert body["ai_status"] == "ok"
    assert body["requirements_count"] == 15
    rewritten = [item for item in body["requirements"] if item["suggested_rewrite"] is not None]
    assert len(rewritten) == 10  # no auto-fan-out: first 10 by position
    assert [item["position"] for item in rewritten] == list(range(10))


# --- failed (fail-open) ------------------------------------------------------


def test_provider_failure_fails_open_with_first_error(ai_client: TestClient) -> None:
    _login_verified(ai_client, "failopen")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter(
        "groq",
        overview=ProviderError("quota", "Quota exceeded. Try again later."),
        expect_key=KEY_GROQ,
    )
    with _adapters(fake):
        response = _analyze(ai_client, True)
    assert response.status_code == 201, response.text  # NEVER fails the analysis
    assert KEY_GROQ not in response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["issues_count"] > 0  # deterministic findings intact
    assert body["ai_status"] == "failed"
    assert body["ai_error"] == "Quota exceeded. Try again later."
    assert body["ai_overview"] is None and body["ai_provider"] is None
    assert all(item["suggested_rewrite"] is None for item in body["requirements"])
    detail = ai_client.get(f"/api/v1/analysis/{body['id']}").json()
    assert detail["ai_status"] == "failed" and detail["ai_error"] == body["ai_error"]


def test_ai_error_capped_at_300_chars(ai_client: TestClient) -> None:
    _login_verified(ai_client, "cap300")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter(
        "groq", overview=ProviderError("unavailable", "E" * 500), expect_key=KEY_GROQ
    )
    with _adapters(fake):
        body = _analyze(ai_client, True).json()
    assert body["ai_status"] == "failed"
    assert body["ai_error"] == "E" * 300  # mirrors analyses.ai_error VARCHAR(300)


def test_chain_falls_back_to_second_provider(ai_client: TestClient) -> None:
    _login_verified(ai_client, "chain")
    groq_row = _create_credential(ai_client, "groq", KEY_GROQ)
    _create_credential(ai_client, "openai", KEY_OPENAI)
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{groq_row['id']}", json={"is_default": True}
        ).status_code
        == 200
    )
    seen: list[str] = []
    failing = _FakeAdapter(
        "groq",
        overview=ProviderError("auth", "Key rejected. Check the key in Settings."),
        expect_key=KEY_GROQ,
        seen=seen,
    )
    fallback = _FakeAdapter(
        "openai", overview="FALLBACK OVERVIEW.", expect_key=KEY_OPENAI, seen=seen
    )
    with _adapters(failing, fallback):
        body = _analyze(ai_client, True).json()
    assert body["ai_status"] == "ok"
    assert body["ai_provider"] == "openai"  # winner recorded, never mixed
    assert body["ai_overview"] == "FALLBACK OVERVIEW."
    assert seen[0] == "groq:overview" and "openai:overview" in seen  # default tried first


def test_chain_exhausted_reports_first_error(ai_client: TestClient) -> None:
    _login_verified(ai_client, "exhaust")
    groq_row = _create_credential(ai_client, "groq", KEY_GROQ)
    _create_credential(ai_client, "openai", KEY_OPENAI)
    assert (
        ai_client.patch(
            f"/api/v1/ai/providers/{groq_row['id']}", json={"is_default": True}
        ).status_code
        == 200
    )
    failing_groq = _FakeAdapter(
        "groq",
        overview=ProviderError("auth", "Groq key rejected."),
        expect_key=KEY_GROQ,
    )
    failing_openai = _FakeAdapter(
        "openai",
        overview=ProviderError("quota", "OpenAI quota exceeded."),
        expect_key=KEY_OPENAI,
    )
    with _adapters(failing_groq, failing_openai):
        body = _analyze(ai_client, True).json()
    assert body["status"] == "analyzed"  # deterministic intact throughout
    assert body["ai_status"] == "failed"
    assert body["ai_error"] == "Groq key rejected."  # first (default) error wins


def test_adapterless_credential_fails_with_guidance(
    ai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Defensive branch pin: all six ship adapters, so force the None path
    # (a not-yet-wired future provider) — the chain names the stored
    # credential's label instead of crying `unconfigured`.
    import app.services.ai_enhancement as enhancement_service

    monkeypatch.setattr(enhancement_service, "resolve_adapter", lambda provider_id: None)
    _login_verified(ai_client, "adapterless")
    _create_credential(ai_client, "groq", KEY_GROQ)
    response = _analyze(ai_client, True)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["ai_status"] == "failed"
    assert body["ai_error"] == "Groq integration isn't available yet."


def test_anthropic_credential_enhances_through_its_adapter(ai_client: TestClient) -> None:
    # Stage 18 re-entry proof: an anthropic credential now flows through
    # the normal chain (default single entry → overview + rewrites).
    _login_verified(ai_client, "anthropic")
    _create_credential(ai_client, "anthropic", KEY_ANTHROPIC)
    fake = _FakeAdapter(
        "anthropic",
        overview="ANTHROPIC OVERVIEW.",
        improvement="REWRITE.",
        expect_key=KEY_ANTHROPIC,
    )
    with _adapters(fake):
        response = _analyze(ai_client, True)
    assert response.status_code == 201, response.text
    assert KEY_ANTHROPIC not in response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["ai_status"] == "ok"
    assert body["ai_provider"] == "anthropic"
    assert body["ai_overview"] == "ANTHROPIC OVERVIEW."
    assert body["ai_error"] is None
    assert body["requirements"][0]["suggested_rewrite"] == "REWRITE."


def test_improvement_failure_skips_only_that_requirement(ai_client: TestClient) -> None:
    _login_verified(ai_client, "besteffor")
    _create_credential(ai_client, "groq", KEY_GROQ)

    def _rewrite(requirement_text: str) -> Any:
        if "MARKER" in requirement_text:
            return ProviderError("bad_response", "Unexpected provider response.")
        return "REWRITE."

    fake = _FakeAdapter("groq", improvement=_rewrite, expect_key=KEY_GROQ)
    text = (
        "FR-001: The system shall respond quickly.\n\n"
        "FR-002: The MARKER system shall log slowly.\n"
    )
    with _adapters(fake):
        body = _analyze(ai_client, True, text=text).json()
    assert body["ai_status"] == "ok"  # one cursed rewrite never fails the run
    assert body["requirements"][0]["suggested_rewrite"] == "REWRITE."
    assert body["requirements"][1]["issues"] != []
    assert body["requirements"][1]["suggested_rewrite"] is None


def test_unexpected_adapter_crash_fails_open_generically(ai_client: TestClient) -> None:
    _login_verified(ai_client, "crash")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter("groq", overview=RuntimeError("boom-internal-trace"), expect_key=KEY_GROQ)
    with _adapters(fake):
        response = _analyze(ai_client, True)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["ai_status"] == "failed"
    assert body["ai_error"] == "AI enhancement failed unexpectedly."
    assert "boom-internal-trace" not in response.text  # internals never leak


def test_vault_outage_fails_open(ai_client: TestClient) -> None:
    _login_verified(ai_client, "vaultout")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter("groq", expect_key=KEY_GROQ)
    os.environ["ENCRYPTION_MASTER_KEY"] = Fernet.generate_key().decode("ascii")
    get_settings.cache_clear()
    try:
        with _adapters(fake):
            response = _analyze(ai_client, True)
    finally:
        os.environ["ENCRYPTION_MASTER_KEY"] = MASTER_KEY
        get_settings.cache_clear()
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "analyzed" and body["score"] is not None
    assert body["ai_status"] == "failed"
    assert body["ai_error"] == "AI enhancement is temporarily unavailable."


# --- document upload ---------------------------------------------------------


def test_document_upload_ai_enhance_runs_the_shared_step(ai_client: TestClient) -> None:
    _login_verified(ai_client, "docai")
    _create_credential(ai_client, "groq", KEY_GROQ)
    fake = _FakeAdapter("groq", overview="DOC OVERVIEW.", expect_key=KEY_GROQ)
    content = b"FR-001: The system shall respond quickly.\n"
    with _adapters(fake):
        response = ai_client.post(
            "/api/v1/documents/upload",
            files={"files": ("srs.txt", content, "text/plain")},
            data={"ai_enhance": "true"},
        )
    assert response.status_code == 201, response.text
    analysis = response.json()["analysis"]
    assert analysis["source_type"] == "document"
    assert analysis["ai_status"] == "ok"
    assert analysis["ai_provider"] == "groq"
    assert analysis["ai_overview"] == "DOC OVERVIEW."


def test_document_upload_defaults_to_skipped(ai_client: TestClient) -> None:
    _login_verified(ai_client, "docskip")
    content = b"FR-001: The system shall respond quickly.\n"
    response = ai_client.post(
        "/api/v1/documents/upload",
        files={"files": ("srs.txt", content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    analysis = response.json()["analysis"]
    assert analysis["source_type"] == "document"
    assert analysis["ai_status"] == "skipped"
