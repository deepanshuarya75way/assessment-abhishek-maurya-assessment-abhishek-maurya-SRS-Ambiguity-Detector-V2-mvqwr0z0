"""Own-profile endpoints (API_CONTRACT §4.7 — Stage 16: profile fields final).

GET/PATCH /settings/profile: verified-only identity reads/writes. Covers auth
gating (401/403), the safe-subset response shape, display-name normalization
(trim, blank→null, explicit null clears), the 100-char cap, and the required
field (absent ≠ clear). No `{id}` exists here — the session IS the selector,
so there is no IDOR surface to test. Privacy/export/purge stay reserved for
Stage 23 (a retention control with no enforcement would be a fake control).
"""

import os
import uuid
from collections.abc import Callable, Coroutine, Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.main import create_app
from app.models import User
from tests.conftest import TEST_DATABASE_URL, db_test_session, run


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
def settings_app(migrated_db: str) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage16-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def settings_client(settings_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(settings_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage16-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw() -> str:
    return "correct-horse-stage16-battery-99"


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
            json={"name": "Stage Sixteen", "email": email, "password": _pw()},
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


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def test_get_profile_requires_session(settings_client: TestClient) -> None:
    response = settings_client.get("/api/v1/settings/profile")
    assert response.status_code == 401
    assert _code(response) == "unauthenticated"


def test_get_profile_requires_verified_email(settings_client: TestClient) -> None:
    _login_unverified(settings_client, "unverified-get")
    response = settings_client.get("/api/v1/settings/profile")
    assert response.status_code == 403
    assert _code(response) == "email_unverified"


def test_get_profile_returns_safe_subset(settings_client: TestClient) -> None:
    email = _login_verified(settings_client, "get-shape")
    response = settings_client.get("/api/v1/settings/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["display_name"] == "Stage Sixteen"
    assert body["is_verified"] is True
    assert body["is_active"] is True
    assert isinstance(body["created_at"], str)
    assert set(body) == {"email", "display_name", "is_verified", "is_active", "created_at"}
    assert "hash" not in response.text
    assert "token" not in response.text


def test_patch_profile_requires_session(settings_client: TestClient) -> None:
    response = settings_client.patch("/api/v1/settings/profile", json={"display_name": "Nope"})
    assert response.status_code == 401
    assert _code(response) == "unauthenticated"


def test_patch_profile_requires_verified_email(settings_client: TestClient) -> None:
    _login_unverified(settings_client, "unverified-patch")
    response = settings_client.patch("/api/v1/settings/profile", json={"display_name": "Nope"})
    assert response.status_code == 403
    assert _code(response) == "email_unverified"


def test_patch_profile_trims_and_persists(settings_client: TestClient) -> None:
    email = _login_verified(settings_client, "patch-trim")
    response = settings_client.patch(
        "/api/v1/settings/profile", json={"display_name": "  Ada Lovelace  "}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Ada Lovelace"
    # Fresh reads (profile AND /auth/me) see the persisted value — no echo.
    assert settings_client.get("/api/v1/settings/profile").json()["display_name"] == "Ada Lovelace"
    assert settings_client.get("/api/v1/auth/me").json()["display_name"] == "Ada Lovelace"

    async def _fetch(session: AsyncSession) -> None:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        assert user.display_name == "Ada Lovelace"

    run(_write(_fetch))


def test_patch_profile_null_clears_name(settings_client: TestClient) -> None:
    _login_verified(settings_client, "patch-clear")
    response = settings_client.patch("/api/v1/settings/profile", json={"display_name": None})
    assert response.status_code == 200
    assert response.json()["display_name"] is None


def test_patch_profile_blank_clears_name(settings_client: TestClient) -> None:
    _login_verified(settings_client, "patch-blank")
    response = settings_client.patch("/api/v1/settings/profile", json={"display_name": "   "})
    assert response.status_code == 200
    assert response.json()["display_name"] is None


def test_patch_profile_rejects_long_name(settings_client: TestClient) -> None:
    _login_verified(settings_client, "patch-long")
    response = settings_client.patch("/api/v1/settings/profile", json={"display_name": "x" * 101})
    assert response.status_code == 400
    assert _code(response) == "validation_error"
    # Rejected writes persist nothing.
    assert settings_client.get("/api/v1/settings/profile").json()["display_name"] == "Stage Sixteen"


def test_patch_profile_requires_the_field(settings_client: TestClient) -> None:
    _login_verified(settings_client, "patch-missing")
    response = settings_client.patch("/api/v1/settings/profile", json={})
    assert response.status_code == 400
    assert _code(response) == "validation_error"


def test_patch_profile_rejects_non_string(settings_client: TestClient) -> None:
    _login_verified(settings_client, "patch-type")
    response = settings_client.patch("/api/v1/settings/profile", json={"display_name": 42})
    assert response.status_code == 400
    assert _code(response) == "validation_error"


def test_unknown_settings_paths_stay_404(settings_client: TestClient) -> None:
    _login_verified(settings_client, "unknown-path")
    assert settings_client.get("/api/v1/settings/privacy").status_code == 200
    assert settings_client.get("/api/v1/settings/profile/other").status_code == 404
    assert settings_client.get("/api/v1/settings/privacy/other").status_code == 404
