"""POST /analysis/{id}/retry-ai (Stage 17: roadmap-20 remainder).

Re-runs ONLY the AI enhancement step through the shared Stage-14 service:
reset (clear AI payload + AI-stamped rewrites) → re-read → enhance. Covers
auth gating (401/403), owner scoping (404 + no oracle), malformed ids (400),
failed→ok recovery, ok→ok overwrite, stale-rewrite clearing on failed
retries, skipped→ok (explicit request), unconfigured stability,
adapterless-credential guidance, deterministic intactness, and the minimal
response shape. Fake
adapters only — no network, ever.
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

KEY_GROQ = "gsk_live_groq_key_for_stage17_tests_aaa1"

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
def retry_app(migrated_db: str) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage17-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    os.environ["ENCRYPTION_MASTER_KEY"] = MASTER_KEY
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def retry_client(retry_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(retry_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage17-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw() -> str:
    return "correct-horse-stage17-battery-99"


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


def _register(client: TestClient, tag: str) -> str:
    email = _email(tag)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"name": "Stage Seventeen", "email": email, "password": _pw()},
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


def _login_unverified(client: TestClient, tag: str) -> str:
    email = _register(client, tag)
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": _pw()}).status_code
        == 200
    )
    return email


def _create_credential(client: TestClient, provider: str, api_key: str) -> dict[str, Any]:
    # Stage 21: CREATE proves keys through the adapter, so tests register an
    # offline fake for the proof call. Scenario-specific fakes still wrap the
    # later analysis/retry calls.
    with _adapters(_FakeAdapter(provider)):
        response = client.post(
            "/api/v1/ai/providers", json={"provider": provider, "api_key": api_key}
        )
    assert response.status_code == 201, response.text
    assert api_key not in response.text
    return dict(response.json())


def _analyze(client: TestClient, ai_enhance: bool) -> Any:
    return client.post(
        "/api/v1/analysis",
        json={"title": "Retry test", "text": SAMPLE_SRS, "options": {"ai_enhance": ai_enhance}},
    )


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


class _FakeAdapter(AIProvider):
    """Scripted generation fake (self-contained copy of the Stage-14 seam:
    `overview`/`improvement` are text or exceptions to raise)."""

    def __init__(self, provider_id: str, *, overview: Any = "Fake overview.") -> None:
        self.id = provider_id
        self.display_name = provider_id.title()
        self.base_url = f"https://{provider_id}.example.com"
        self._overview = overview

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
        _ = (api_key, payload, timeout_s)
        if isinstance(self._overview, Exception):
            raise self._overview
        return AITextResult(text=str(self._overview), model="fake-model", latency_ms=1)

    async def generate_improvement(
        self, api_key: str, payload: ImprovementPayload, *, timeout_s: int
    ) -> AITextResult:
        _ = (api_key, payload, timeout_s)
        return AITextResult(text="Fake rewrite.", model="fake-model", latency_ms=1)


@contextmanager
def _adapters(*fakes: _FakeAdapter) -> Generator[None, None, None]:
    for fake in fakes:
        register_adapter(fake)
    try:
        yield
    finally:
        for fake in fakes:
            unregister_adapter(fake.id)


def test_retry_requires_session(retry_client: TestClient) -> None:
    response = retry_client.post(f"/api/v1/analysis/{uuid.uuid4()}/retry-ai")
    assert response.status_code == 401
    assert _code(response) == "unauthenticated"


def test_retry_requires_verified_email(retry_client: TestClient) -> None:
    _login_unverified(retry_client, "unverified")
    response = retry_client.post(f"/api/v1/analysis/{uuid.uuid4()}/retry-ai")
    assert response.status_code == 403
    assert _code(response) == "email_unverified"


def test_retry_missing_analysis_404s(retry_client: TestClient) -> None:
    _login_verified(retry_client, "missing")
    response = retry_client.post(f"/api/v1/analysis/{uuid.uuid4()}/retry-ai")
    assert response.status_code == 404
    assert _code(response) == "analysis_not_found"


def test_retry_malformed_id_400s(retry_client: TestClient) -> None:
    _login_verified(retry_client, "malformed")
    response = retry_client.post("/api/v1/analysis/not-a-uuid/retry-ai")
    assert response.status_code == 400
    assert _code(response) == "validation_error"


def test_retry_ai_dedicated_bucket_rate_limits(
    retry_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_verified(retry_client, "ratelimit")
    created = _analyze(retry_client, False)
    analysis_id = str(created.json()["id"])
    monkeypatch.setenv("RATE_LIMIT_AI_RETRY_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        assert retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai").status_code == 200
        assert retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai").status_code == 200
        limited = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
        assert limited.status_code == 429
        assert _code(limited) == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1
    finally:
        get_settings.cache_clear()


def test_retry_foreign_analysis_404s_without_oracle(retry_client: TestClient) -> None:
    _login_verified(retry_client, "owner")
    analysis_id = str(_analyze(retry_client, False).json()["id"])
    _login_verified(retry_client, "stranger")  # same client, new session jar
    foreign = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    missing = retry_client.post(f"/api/v1/analysis/{uuid.uuid4()}/retry-ai")
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json()  # byte-identical: no oracle


def test_retry_failed_becomes_ok(retry_client: TestClient) -> None:
    _login_verified(retry_client, "failed-ok")
    _create_credential(retry_client, "groq", KEY_GROQ)
    with _adapters(_FakeAdapter("groq", overview=ProviderError("unavailable", "Boom."))):
        created = _analyze(retry_client, True)
    assert created.json()["ai_status"] == "failed"
    analysis_id = str(created.json()["id"])
    with _adapters(_FakeAdapter("groq", overview="Recovered overview.")):
        response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert response.status_code == 200
    assert response.json() == {
        "ai_status": "ok",
        "ai_overview": "Recovered overview.",
        "ai_provider": "groq",
        "ai_error": None,
    }
    detail = retry_client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert detail["ai_status"] == "ok"
    assert any(
        (item["suggested_rewrite"] or "") != "" for item in detail["requirements"]
    ), "ok retry persists rewrites"


def test_retry_ok_overwrites_overview(retry_client: TestClient) -> None:
    _login_verified(retry_client, "ok-ok")
    _create_credential(retry_client, "groq", KEY_GROQ)
    with _adapters(_FakeAdapter("groq", overview="First overview.")):
        created = _analyze(retry_client, True)
    analysis_id = str(created.json()["id"])
    assert created.json()["ai_overview"] == "First overview."
    with _adapters(_FakeAdapter("groq", overview="Second overview.")):
        response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert response.json()["ai_overview"] == "Second overview."
    assert (
        retry_client.get(f"/api/v1/analysis/{analysis_id}").json()["ai_overview"]
        == "Second overview."
    )


def test_retry_failed_clears_stale_rewrites(retry_client: TestClient) -> None:
    _login_verified(retry_client, "stale-rewrites")
    _create_credential(retry_client, "groq", KEY_GROQ)
    with _adapters(_FakeAdapter("groq", overview="Good overview.")):
        created = _analyze(retry_client, True)
    analysis_id = str(created.json()["id"])
    before = retry_client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert any(item["suggested_rewrite"] is not None for item in before["requirements"])
    with _adapters(_FakeAdapter("groq", overview=ProviderError("unavailable", "Provider down."))):
        response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert response.json()["ai_status"] == "failed"
    assert response.json()["ai_overview"] is None
    after = retry_client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert after["ai_status"] == "failed"
    assert after["ai_error"] == "Provider down."
    assert all(item["suggested_rewrite"] is None for item in after["requirements"])
    assert all(item["suggestion_source"] is None for item in after["requirements"])


def test_retry_skipped_runs_the_step(retry_client: TestClient) -> None:
    _login_verified(retry_client, "skipped-ok")
    _create_credential(retry_client, "groq", KEY_GROQ)
    with _adapters(_FakeAdapter("groq", overview="Skipped no more.")):
        created = _analyze(retry_client, False)
    assert created.json()["ai_status"] == "skipped"
    analysis_id = str(created.json()["id"])
    with _adapters(_FakeAdapter("groq", overview="Skipped no more.")):
        response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert response.json()["ai_status"] == "ok"
    assert response.json()["ai_overview"] == "Skipped no more."


def test_retry_unconfigured_stays_unconfigured(retry_client: TestClient) -> None:
    _login_verified(retry_client, "unconfigured")
    created = _analyze(retry_client, True)  # no credentials at all
    assert created.json()["ai_status"] == "unconfigured"
    analysis_id = str(created.json()["id"])
    response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert response.status_code == 200
    assert response.json() == {
        "ai_status": "unconfigured",
        "ai_overview": None,
        "ai_provider": None,
        "ai_error": None,
    }


def test_retry_adapterless_credential_reports_failed(
    retry_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Defensive branch pin: no adapter resolves (forced None), so both the
    # initial run and the retry fail open with guidance — deterministic
    # intact throughout.
    import app.services.ai_enhancement as enhancement_service

    monkeypatch.setattr(enhancement_service, "resolve_adapter", lambda provider_id: None)
    _login_verified(retry_client, "adapterless")
    _create_credential(retry_client, "groq", KEY_GROQ)
    created = _analyze(retry_client, True)
    analysis_id = str(created.json()["id"])
    response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert response.json()["ai_status"] == "failed"
    assert "isn't available yet" in (response.json()["ai_error"] or "")


def test_retry_keeps_deterministic_intact(retry_client: TestClient) -> None:
    _login_verified(retry_client, "deterministic")
    _create_credential(retry_client, "groq", KEY_GROQ)
    with _adapters(_FakeAdapter("groq", overview=ProviderError("unavailable", "Down."))):
        created = _analyze(retry_client, True)
    analysis_id = str(created.json()["id"])
    before = retry_client.get(f"/api/v1/analysis/{analysis_id}").json()
    with _adapters(_FakeAdapter("groq", overview="Shiny overview.")):
        response = retry_client.post(f"/api/v1/analysis/{analysis_id}/retry-ai")
    assert set(response.json()) == {"ai_status", "ai_overview", "ai_provider", "ai_error"}
    after = retry_client.get(f"/api/v1/analysis/{analysis_id}").json()
    for key in ("score", "band", "requirements_count", "issues_count", "score_breakdown", "health"):
        assert after[key] == before[key], key
    assert [(item["text"], item["score"]) for item in after["requirements"]] == [
        (item["text"], item["score"]) for item in before["requirements"]
    ]
    before_issues = [
        (issue["category"], issue["severity"], issue["phrase"])
        for item in before["requirements"]
        for issue in item["issues"]
    ]
    after_issues = [
        (issue["category"], issue["severity"], issue["phrase"])
        for item in after["requirements"]
        for issue in item["issues"]
    ]
    assert after_issues == before_issues
