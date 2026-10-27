"""Auth API E2E: register → verify → login → refresh → logout + recovery flows.

HTTP-level contract tests (API_CONTRACT §4.2): status codes, envelope codes,
cookie attributes, CSRF origin checks, and rate-limit wiring. Email is captured
by an in-memory fake (never real sends); emailed link tokens come from it.
"""

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.core.security import create_access_token
from app.email.base import (
    TEMPLATE_ACCOUNT_EXISTS,
    TEMPLATE_RESET_PASSWORD,
    TEMPLATE_SECURITY_NOTICE,
    TEMPLATE_VERIFY_EMAIL,
    EmailMessage,
    EmailService,
)
from app.main import create_app
from app.models import User
from tests.conftest import TEST_DATABASE_URL, db_test_session, run

# NOTE: credential literals never sit in `password`-named bindings (S106); the
# _pw() helper builds them so every payload value is a call result, not a literal.


class FakeEmailService(EmailService):
    """In-memory email port (outbox inspection replaces link clicking)."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def tokens(self, template: str) -> list[str]:
        return [
            m.context["token"] for m in self.sent if m.template == template and "token" in m.context
        ]

    def count(self, template: str) -> int:
        return sum(1 for m in self.sent if m.template == template)


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
def auth_app(migrated_db: str) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage04-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    get_settings.cache_clear()
    app = create_app()
    app.state.email_service = FakeEmailService()
    return app


@pytest.fixture()
def auth_client(auth_app: FastAPI) -> Generator[TestClient, None, None]:
    # Context-manager form: lifespan shutdown disposes the app engine, so no
    # pool leaks across tests (each TestClient owns its event loop).
    with TestClient(auth_app) as client:
        yield client


def _outbox(auth_app: FastAPI) -> FakeEmailService:
    service = auth_app.state.email_service
    assert isinstance(service, FakeEmailService)
    return service


def _email(tag: str) -> str:
    return f"stage04-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw(tag: str = "staple") -> str:
    return f"correct-horse-{tag}-battery-99"


def _register(client: TestClient, email: str, **extra: object) -> Response:
    payload: dict[str, object] = {"name": "Stage Four", "email": email, "password": _pw()}
    payload.update(extra)
    return client.post("/api/v1/auth/register", json=payload)


def _login(client: TestClient, email: str, password: str) -> Response:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _set_cookies(client: TestClient, **cookies: str) -> None:
    """Replace the jar with exactly these cookies. http.cookiejar stores the
    dotless `testserver` host as `testserver.local` — a manually-set cookie
    with any other domain is silently never sent."""
    client.cookies.clear()
    for name, value in cookies.items():
        client.cookies.set(name, value, domain="testserver.local", path="/")


def _set_cookie_headers(resp: Response) -> list[str]:
    return resp.headers.get_list("set-cookie")


async def _set_user_active(email: str, active: bool) -> None:
    """Direct DB write WITHOUT the conftest truncate (db_test_session wipes on exit)."""
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            user = (await session.execute(select(User).where(User.email == email))).scalar_one()
            user.is_active = active
            await session.commit()
    finally:
        await engine.dispose()


# --- register ---------------------------------------------------------------


def test_register_creates_unverified_user_without_session(
    auth_client: TestClient, auth_app: FastAPI
) -> None:
    email = _email("reg")
    resp = _register(auth_client, email)
    assert resp.status_code == 201
    assert set(resp.json()) == {"id", "email", "is_verified"}
    assert resp.json()["email"] == email
    assert resp.json()["is_verified"] is False
    assert _set_cookie_headers(resp) == []  # register never logs in (contract §4.2)
    outbox = _outbox(auth_app)
    assert outbox.count(TEMPLATE_VERIFY_EMAIL) == 1
    assert len(outbox.tokens(TEMPLATE_VERIFY_EMAIL)[0]) >= 40


def test_register_normalizes_email(auth_client: TestClient) -> None:
    resp = _register(auth_client, "  Case@Test-Example.COM ")
    assert resp.status_code == 201
    assert resp.json()["email"] == "case@test-example.com"
    assert _login(auth_client, "CASE@test-example.com", _pw()).status_code == 200


def test_register_duplicate_returns_synthetic_201(
    auth_client: TestClient, auth_app: FastAPI
) -> None:
    email = _email("dup")
    first_id = _register(auth_client, email).json()["id"]
    # Differently-cased retry hits the SAME account (normalization in the check).
    resp = _register(auth_client, email.upper())
    assert resp.status_code == 201
    assert resp.json()["is_verified"] is False
    assert resp.json()["id"] != first_id  # synthetic identity, not the real row
    outbox = _outbox(auth_app)
    assert outbox.count(TEMPLATE_VERIFY_EMAIL) == 1  # no second verify mail
    assert outbox.count(TEMPLATE_ACCOUNT_EXISTS) == 1
    assert outbox.sent[-1].to == email
    assert _login(auth_client, email, _pw()).status_code == 200  # original intact


def test_register_rejects_common_password(auth_client: TestClient) -> None:
    resp = _register(
        auth_client,
        _email("weak"),
        password="password1234",  # noqa: S106 — intentional weak fixture
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "password_too_weak"


def test_register_rejects_password_containing_email(auth_client: TestClient) -> None:
    resp = _register(
        auth_client,
        "robertson@example.com",
        password="xx-robertson-99!",  # noqa: S106 — intentional weak fixture
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "password_too_weak"


def test_register_short_password_is_validation_error(auth_client: TestClient) -> None:
    resp = _register(
        auth_client,
        _email("short"),
        password="too-short",  # noqa: S106 — intentional short fixture
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_register_invalid_email_is_validation_error(auth_client: TestClient) -> None:
    resp = _register(auth_client, "not-an-email")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


# --- login ------------------------------------------------------------------


def test_login_unverified_ok_sets_session_cookies(auth_client: TestClient) -> None:
    email = _email("login")
    _register(auth_client, email)
    resp = _login(auth_client, email, _pw())
    assert resp.status_code == 200
    assert resp.json()["is_verified"] is False  # unverified CAN log in (gated later)
    jar = resp.cookies
    assert jar.get("access_token") and jar.get("refresh_token")
    raw = " ".join(_set_cookie_headers(resp))
    assert "HttpOnly" in raw and "Path=/" in raw and "Max-Age=900" in raw
    assert "Max-Age=2592000" in raw  # 30-day refresh
    assert "Secure" not in raw  # local env: Secure only in production
    assert "SameSite=lax" in raw or "SameSite=Lax" in raw


def test_login_wrong_password_and_unknown_email_are_indistinguishable(
    auth_client: TestClient,
) -> None:
    email = _email("bad")
    _register(auth_client, email)
    bad_pw = _login(auth_client, email, _pw("wrong"))
    unknown = _login(auth_client, _email("nobody"), _pw())
    for resp in (bad_pw, unknown):
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"
    assert bad_pw.json() == unknown.json()  # byte-identical: no oracle


def test_login_disabled_account_is_403(auth_client: TestClient) -> None:
    email = _email("off")
    _register(auth_client, email)
    run(_set_user_active(email, False))
    resp = _login(auth_client, email, _pw())
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "account_disabled"


# --- me ---------------------------------------------------------------------


def test_me_returns_profile(auth_client: TestClient) -> None:
    email = _email("me")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert set(resp.json()) == {
        "id",
        "email",
        "display_name",
        "is_verified",
        "is_active",
        "created_at",
    }
    assert resp.json()["email"] == email
    assert resp.json()["display_name"] == "Stage Four"


def test_me_requires_session(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"
    forged = "forged-token"
    _set_cookies(auth_client, access_token=forged)
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 401  # forged session cookie is 401, never 400/500


def test_me_expired_access_token_is_401(auth_client: TestClient) -> None:
    email = _email("exp")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    user_id = uuid.UUID(auth_client.get("/api/v1/auth/me").json()["id"])
    _set_cookies(auth_client, access_token=create_access_token(user_id, expires_minutes=-1))
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# --- refresh ----------------------------------------------------------------


def test_refresh_rotates_token_pair(auth_client: TestClient) -> None:
    email = _email("rot")
    _register(auth_client, email)
    first_refresh = _login(auth_client, email, _pw()).cookies.get("refresh_token")
    assert first_refresh
    resp = auth_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    second_refresh = resp.cookies.get("refresh_token")
    assert second_refresh and second_refresh != first_refresh
    assert resp.cookies.get("access_token")  # fresh access too


def test_refresh_reuse_revokes_whole_family(auth_client: TestClient) -> None:
    email = _email("reuse")
    _register(auth_client, email)
    token_a = _login(auth_client, email, _pw()).cookies.get("refresh_token")
    assert token_a
    token_b = auth_client.post("/api/v1/auth/refresh").cookies.get("refresh_token")
    assert token_b
    _set_cookies(auth_client, refresh_token=token_a)  # replay the rotated token
    replay = auth_client.post("/api/v1/auth/refresh")
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "invalid_token"
    assert "revoked" in replay.json()["error"]["message"].lower()
    _set_cookies(auth_client, refresh_token=token_b)  # family is dead too
    assert auth_client.post("/api/v1/auth/refresh").status_code == 400


def test_refresh_without_cookie_or_unknown_token_is_400(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    resp = auth_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_token"
    unknown = "unguessable-but-unknown-token"
    _set_cookies(auth_client, refresh_token=unknown)
    assert auth_client.post("/api/v1/auth/refresh").status_code == 400


# --- logout -----------------------------------------------------------------


def test_logout_revokes_session_and_clears_cookies(auth_client: TestClient) -> None:
    email = _email("out")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert resp.content == b""
    assert any("Max-Age=0" in c for c in _set_cookie_headers(resp))
    assert "access_token" not in auth_client.cookies  # jar dropped the cookies
    assert auth_client.post("/api/v1/auth/refresh").status_code == 400


def test_logout_is_idempotent_without_cookies(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    assert auth_client.post("/api/v1/auth/logout").status_code == 204
    assert auth_client.post("/api/v1/auth/logout").status_code == 204


def test_logout_works_with_expired_access_token(auth_client: TestClient) -> None:
    email = _email("outexp")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    live_refresh = auth_client.cookies.get("refresh_token")
    assert live_refresh
    stale = "expired-or-garbage"
    _set_cookies(auth_client, access_token=stale, refresh_token=live_refresh)
    assert auth_client.post("/api/v1/auth/logout").status_code == 204
    assert auth_client.post("/api/v1/auth/refresh").status_code == 400


# --- verify / resend ----------------------------------------------------------


def test_verify_email_activates_and_logs_in(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("ver")
    _register(auth_client, email)
    (token,) = _outbox(auth_app).tokens(TEMPLATE_VERIFY_EMAIL)
    resp = auth_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["is_verified"] is True
    assert resp.cookies.get("access_token")  # auto-login per contract
    assert auth_client.get("/api/v1/auth/me").json()["is_verified"] is True
    assert _outbox(auth_app).count(TEMPLATE_SECURITY_NOTICE) == 1
    assert auth_client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


def test_verify_email_unknown_and_malformed_tokens_are_400(auth_client: TestClient) -> None:
    unknown = auth_client.post("/api/v1/auth/verify-email", json={"token": "0" * 43})
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "invalid_token"
    # Malformed tokens never reach the service (cheap schema rejection).
    malformed = auth_client.post("/api/v1/auth/verify-email", json={"token": "no-such-token"})
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "validation_error"


def test_resend_supersedes_old_token(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("rs")
    _register(auth_client, email)
    outbox = _outbox(auth_app)
    (old_token,) = outbox.tokens(TEMPLATE_VERIFY_EMAIL)
    resp = auth_client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert resp.status_code == 202
    assert resp.json() == {}
    (new_token,) = outbox.tokens(TEMPLATE_VERIFY_EMAIL)[1:]
    assert new_token != old_token
    assert (
        auth_client.post("/api/v1/auth/verify-email", json={"token": old_token}).status_code == 400
    )
    assert (
        auth_client.post("/api/v1/auth/verify-email", json={"token": new_token}).status_code == 200
    )


def test_resend_is_silent_for_unknown_and_verified(
    auth_client: TestClient, auth_app: FastAPI
) -> None:
    outbox = _outbox(auth_app)
    assert (
        auth_client.post(
            "/api/v1/auth/resend-verification", json={"email": _email("ghost")}
        ).status_code
        == 202
    )
    assert outbox.sent == []
    email = _email("already")
    _register(auth_client, email)
    (token,) = outbox.tokens(TEMPLATE_VERIFY_EMAIL)
    auth_client.post("/api/v1/auth/verify-email", json={"token": token})
    outbox.sent.clear()
    assert (
        auth_client.post("/api/v1/auth/resend-verification", json={"email": email}).status_code
        == 202
    )
    assert outbox.sent == []  # verified: silent 202, no oracle


# --- forgot / reset -----------------------------------------------------------


def test_forgot_and_reset_full_cycle(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("cycle")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    outbox = _outbox(auth_app)
    assert (
        auth_client.post("/api/v1/auth/forgot-password", json={"email": email}).status_code == 202
    )
    (token,) = outbox.tokens(TEMPLATE_RESET_PASSWORD)
    new_pw = _pw("brand-new")
    resp = auth_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}
    )
    assert resp.status_code == 200
    assert outbox.count(TEMPLATE_SECURITY_NOTICE) == 1
    assert _login(auth_client, email, _pw()).status_code == 401  # old password dead
    assert _login(auth_client, email, new_pw).status_code == 200
    assert (  # token single-use
        auth_client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}
        ).status_code
        == 400
    )


def test_reset_logs_out_everywhere(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("rsevery")
    _register(auth_client, email)
    _login(auth_client, email, _pw())  # jar holds a live refresh token
    auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    (token,) = _outbox(auth_app).tokens(TEMPLATE_RESET_PASSWORD)
    auth_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": _pw("fresh")}
    )
    assert auth_client.post("/api/v1/auth/refresh").status_code == 400


def test_forgot_unknown_email_is_silent_202(auth_client: TestClient, auth_app: FastAPI) -> None:
    resp = auth_client.post("/api/v1/auth/forgot-password", json={"email": _email("ghost")})
    assert resp.status_code == 202
    assert resp.json() == {}
    assert _outbox(auth_app).sent == []


def test_forgot_supersedes_previous_token(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("fgsup")
    _register(auth_client, email)
    outbox = _outbox(auth_app)
    auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    old_token, new_token = outbox.tokens(TEMPLATE_RESET_PASSWORD)
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": old_token, "new_password": _pw("good-one")},
        ).status_code
        == 400
    )
    assert (
        auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": new_token, "new_password": _pw("good-one")},
        ).status_code
        == 200
    )


def test_reset_weak_password_keeps_token_usable(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("weakrst")
    _register(auth_client, email)
    auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    (token,) = _outbox(auth_app).tokens(TEMPLATE_RESET_PASSWORD)
    weak = auth_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "password1234"}
    )
    assert weak.status_code == 400
    assert weak.json()["error"]["code"] == "password_too_weak"
    assert (  # no partial state: the token still works
        auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": _pw("finally")},
        ).status_code
        == 200
    )


# --- change password ----------------------------------------------------------


def test_change_password_cycle(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("chg")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    new_pw = _pw("rotated")
    resp = auth_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": _pw(), "new_password": new_pw},
    )
    assert resp.status_code == 200
    assert _outbox(auth_app).count(TEMPLATE_SECURITY_NOTICE) == 1
    assert auth_client.post("/api/v1/auth/refresh").status_code == 400  # others logged out
    assert _login(auth_client, email, _pw()).status_code == 401
    assert _login(auth_client, email, new_pw).status_code == 200


def test_change_password_wrong_current_is_400(auth_client: TestClient) -> None:
    email = _email("chg400")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    resp = auth_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": _pw("not-it"), "new_password": _pw("new-one")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "current_password_incorrect"


def test_change_password_requires_session(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    resp = auth_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": _pw(), "new_password": _pw("new-one")},
    )
    assert resp.status_code == 401


# --- delete account -----------------------------------------------------------


def test_delete_account_purges_and_logs_out(auth_client: TestClient, auth_app: FastAPI) -> None:
    email = _email("bye")
    password = _pw()
    _register(auth_client, email)
    _login(auth_client, email, password)
    outbox = _outbox(auth_app)
    outbox.sent.clear()
    resp = auth_client.request("DELETE", "/api/v1/auth/account", json={"confirmation": "DELETE"})
    assert resp.status_code == 204
    assert outbox.count(TEMPLATE_SECURITY_NOTICE) == 1  # farewell notice
    assert auth_client.get("/api/v1/auth/me").status_code == 401
    assert _login(auth_client, email, password).status_code == 401
    assert (  # the address is free again (genuinely deleted, not flagged)
        _register(auth_client, email).json()["is_verified"] is False
    )
    assert outbox.count(TEMPLATE_VERIFY_EMAIL) == 1


def test_delete_account_rejects_bad_confirmation(auth_client: TestClient) -> None:
    email = _email("byeno")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    resp = auth_client.request("DELETE", "/api/v1/auth/account", json={"confirmation": "please"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"
    assert auth_client.get("/api/v1/auth/me").status_code == 200  # untouched


def test_delete_account_requires_session(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    resp = auth_client.request("DELETE", "/api/v1/auth/account", json={"confirmation": "DELETE"})
    assert resp.status_code == 401


# --- CSRF origin check --------------------------------------------------------


def test_mutations_reject_foreign_origin(auth_client: TestClient) -> None:
    evil = {"Origin": "https://evil.test"}
    resp = auth_client.post(
        "/api/v1/auth/register",
        json={"name": "X", "email": _email("csrf"), "password": _pw()},
        headers=evil,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
    evil_ref = auth_client.post(
        "/api/v1/auth/login",
        json={"email": _email("csrf"), "password": _pw()},
        headers={"Referer": "https://evil.test/phish"},
    )
    assert evil_ref.status_code == 403
    email = _email("csrf2")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    authed = auth_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": _pw(), "new_password": _pw("new-one")},
        headers=evil,
    )
    assert authed.status_code == 403  # the authenticated guard checks too


def test_mutations_allow_listed_origin_and_safe_get(
    auth_client: TestClient,
) -> None:
    listed = {"Origin": "http://localhost:3000"}
    assert (
        auth_client.post(
            "/api/v1/auth/register",
            json={"name": "Y", "email": _email("ok"), "password": _pw()},
            headers=listed,
        ).status_code
        == 201
    )
    email = _email("okget")
    _register(auth_client, email)
    _login(auth_client, email, _pw())
    # GET /me is a safe method: exempt from the origin check by design.
    assert (
        auth_client.get("/api/v1/auth/me", headers={"Origin": "https://evil.test"}).status_code
        == 200
    )


# --- rate limiting ------------------------------------------------------------


def test_auth_rate_limit_returns_429_with_retry_after(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "3")
    get_settings.cache_clear()
    try:
        email = _email("rl")
        for _ in range(3):
            assert _register(auth_client, email).status_code == 201
        limited = _register(auth_client, email)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1
    finally:
        get_settings.cache_clear()


# --- production cookie posture -------------------------------------------------


def test_secure_cookie_flag_in_production(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = migrated_db
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-only-dummy-key")

    os.environ["JWT_SECRET"] = "stage04-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    get_settings.cache_clear()
    try:
        app = create_app()
        app.state.email_service = FakeEmailService()
        with TestClient(app) as client:
            email = _email("prod")
            assert _register(client, email).status_code == 201
            raw = " ".join(_set_cookie_headers(_login(client, email, _pw())))
            assert "Secure" in raw and "HttpOnly" in raw
    finally:
        get_settings.cache_clear()
