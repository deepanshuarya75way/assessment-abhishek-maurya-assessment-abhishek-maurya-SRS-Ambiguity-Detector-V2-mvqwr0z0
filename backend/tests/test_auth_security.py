"""Auth primitives: password hashing, tokens, JWTs, rate buckets, email rendering.

No database here — pure unit coverage for `core/security.py`,
`core/rate_limit.py`, and the `email/` package (adapters included, with the
HTTP layer doubled — never real network in tests).
"""

import logging
import os
from collections.abc import Generator
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.rate_limit import check_rate_limit, reset_rate_limiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_token,
    hash_ip,
    hash_password,
    hash_token,
    is_common_password,
    normalize_email,
    verify_password,
    verify_token_hash,
)
from app.email import get_email_service
from app.email.base import (
    TEMPLATE_ACCOUNT_EXISTS,
    TEMPLATE_RESET_PASSWORD,
    TEMPLATE_SECURITY_NOTICE,
    TEMPLATE_VERIFY_EMAIL,
    EmailMessage,
    render_email,
)
from app.email.console import ConsoleEmailService
from app.email.resend import ResendEmailService
from app.exceptions import InvalidTokenError, RateLimitedError
from tests.conftest import run

os.environ.setdefault("JWT_SECRET", "stage04-test-jwt-secret-32-bytes-minimum")
# Collection imports app.main (which caches settings), so clear after setting.
get_settings.cache_clear()

_TEST_UID = "12345678-1234-5678-1234-567812345678"


@pytest.fixture(autouse=True)
def _fresh_limiter() -> Generator[None, None, None]:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


# --- email normalization ------------------------------------------------------


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"
    assert normalize_email("plain@example.com") == "plain@example.com"


# --- passwords ----------------------------------------------------------------


def test_password_hash_roundtrip() -> None:
    async def _go() -> None:
        hashed = await hash_password("correct-horse-battery-staple-99")
        assert hashed != "correct-horse-battery-staple-99"
        assert hashed.startswith("$argon2id$")
        assert await verify_password("correct-horse-battery-staple-99", hashed) is True
        assert await verify_password("wrong-password-entirely", hashed) is False

    run(_go())


def test_password_verify_fails_closed_on_corrupt_hash() -> None:
    async def _go() -> None:
        assert await verify_password("anything", "not-a-valid-hash") is False
        assert await verify_password("anything", "") is False

    run(_go())


def test_common_password_denylist_is_case_insensitive() -> None:
    assert is_common_password("Password1234") is True
    assert is_common_password("QWERTY123456") is True
    assert is_common_password("x7#Kp9!mV2@qRz correct horse") is False


# --- random tokens --------------------------------------------------------------


def test_generate_token_is_256_bit_urlsafe() -> None:
    seen = {generate_token() for _ in range(3)}
    assert len(seen) == 3
    for token in seen:
        assert len(token) == 43  # token_urlsafe(32)
        assert all(c.isalnum() or c in "-_" for c in token)


def test_token_hash_is_deterministic_sha256_hex() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert len(hash_token("abc")) == 64
    assert hash_token("abc") != hash_token("abd")
    assert verify_token_hash("abc", hash_token("abc")) is True
    assert verify_token_hash("abc", hash_token("abd")) is False


def test_hash_ip_is_stable_and_one_way() -> None:
    assert hash_ip("203.0.113.7") == hash_ip("203.0.113.7")
    assert len(hash_ip("203.0.113.7")) == 64
    assert "203.0.113.7" not in hash_ip("203.0.113.7")


# --- access JWTs -----------------------------------------------------------------


def test_access_token_roundtrip() -> None:
    import uuid

    token = create_access_token(uuid.UUID(_TEST_UID))
    assert decode_access_token(token) == uuid.UUID(_TEST_UID)


def test_access_token_rejects_forged_expired_and_typeless() -> None:
    import uuid

    secret = os.environ["JWT_SECRET"]
    forged = jwt.encode(
        {"sub": _TEST_UID, "type": "access"},
        "wrong-secret-0000000000000000000000",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)
    with pytest.raises(InvalidTokenError):
        decode_access_token("garbage-token")
    with pytest.raises(InvalidTokenError):  # expired
        decode_access_token(create_access_token(uuid.UUID(_TEST_UID), expires_minutes=-1))
    typeless = jwt.encode({"sub": _TEST_UID}, secret, algorithm="HS256")  # no type
    with pytest.raises(InvalidTokenError):
        decode_access_token(typeless)
    no_sub = jwt.encode({"type": "access"}, secret, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(no_sub)
    bad_sub = jwt.encode({"sub": "not-a-uuid", "type": "access"}, secret, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad_sub)


def test_access_token_requires_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            create_access_token(uuid.UUID(_TEST_UID))
    finally:
        get_settings.cache_clear()


def test_short_jwt_secret_rejected_at_settings_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(ValidationError):
        Settings()


# --- rate limiter -------------------------------------------------------------------


def test_rate_limiter_exhausts_per_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        check_rate_limit("key-a")
        check_rate_limit("key-a")
        check_rate_limit("key-b")  # independent bucket: unaffected
        with pytest.raises(RateLimitedError) as exc_info:
            check_rate_limit("key-a")
        assert exc_info.value.retry_after_seconds >= 1
    finally:
        get_settings.cache_clear()


def test_rate_limiter_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "1")
    get_settings.cache_clear()
    try:
        for _ in range(5):
            check_rate_limit("disabled-key")  # must never raise
    finally:
        get_settings.cache_clear()


# --- email templates ------------------------------------------------------------------


def test_render_verify_and_reset_links() -> None:
    subject, body = render_email(
        EmailMessage(
            to="a@example.com",
            template=TEMPLATE_VERIFY_EMAIL,
            context={"token": "tok123", "name": "Ada", "expiry_hours": "24"},
        ),
        "http://localhost:3000/",
    )
    assert "Verify your email" in subject
    assert "/verify-email?token=tok123" in body
    assert "http://localhost:3000/verify-email" in body  # trailing slash tolerated
    subject, body = render_email(
        EmailMessage(
            to="a@example.com",
            template=TEMPLATE_RESET_PASSWORD,
            context={"token": "tok456", "expiry_minutes": "60"},
        ),
        "http://localhost:3000",
    )
    assert "Reset your password" in subject
    assert "/reset-password?token=tok456" in body


def test_render_escapes_user_controlled_content() -> None:
    _, body = render_email(
        EmailMessage(
            to="a@example.com",
            template=TEMPLATE_VERIFY_EMAIL,
            context={"token": "t", "name": "<script>alert(1)</script>"},
        ),
        "http://localhost:3000",
    )
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_render_notice_and_account_exists() -> None:
    subject, body = render_email(
        EmailMessage(
            to="a@example.com",
            template=TEMPLATE_SECURITY_NOTICE,
            context={"title": "Password changed", "detail": "All sessions signed out."},
        ),
        "http://localhost:3000",
    )
    assert "Password changed" in subject and "signed out" in body
    subject, body = render_email(
        EmailMessage(to="a@example.com", template=TEMPLATE_ACCOUNT_EXISTS, context={}),
        "http://localhost:3000",
    )
    assert "already have an account" in subject
    assert "/login" in body


def test_render_unknown_template_raises() -> None:
    with pytest.raises(ValueError, match="Unknown email template"):
        render_email(EmailMessage(to="a@example.com", template="nope", context={}), "http://x")


# --- console adapter ---------------------------------------------------------------------


def test_console_adapter_writes_outbox_file_but_logs_no_secrets(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    from pathlib import Path

    outbox = Path(str(tmp_path))
    service = ConsoleEmailService(str(outbox), "http://localhost:3000")
    link_fixture = "super-secret-link-token"

    async def _go() -> None:
        with caplog.at_level(logging.INFO):
            await service.send(
                EmailMessage(
                    to="dev@example.com",
                    template=TEMPLATE_VERIFY_EMAIL,
                    context={"token": link_fixture, "name": "Dev"},
                )
            )

    run(_go())
    files = list(outbox.glob("*.html"))
    assert len(files) == 1 and "verify_email" in files[0].name
    assert link_fixture in files[0].read_text(encoding="utf-8")  # file keeps the link
    messages = [r.getMessage() for r in caplog.records]
    assert any("DEV-ONLY email" in m for m in messages)  # capture proven
    assert all(link_fixture not in m for m in messages)  # logs stay metadata-only


# --- resend adapter (HTTP doubled — no network) --------------------------------------


class _FakeAsyncClient:
    """httpx.AsyncClient double with class-level scripting per test."""

    instances: ClassVar[list["_FakeAsyncClient"]] = []
    status_code: ClassVar[int] = 200
    explode: ClassVar[bool] = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        self.calls: list[dict[str, Any]] = []
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def post(self, url: object, headers: object = None, json: object = None) -> Any:
        if _FakeAsyncClient.explode:
            raise httpx.ConnectError("simulated outage")
        self.calls.append({"url": url, "headers": headers, "json": json})
        return SimpleNamespace(status_code=_FakeAsyncClient.status_code)


@pytest.fixture()
def _fake_http(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    _FakeAsyncClient.instances.clear()
    _FakeAsyncClient.status_code = 200
    _FakeAsyncClient.explode = False
    monkeypatch.setattr("app.email.resend.httpx.AsyncClient", _FakeAsyncClient)
    yield
    _FakeAsyncClient.instances.clear()


def _resend_service() -> ResendEmailService:
    return ResendEmailService("test-key", "SRS <noreply@example.com>", "http://localhost:3000")


def test_resend_success_posts_expected_payload(_fake_http: None) -> None:
    _ = _fake_http

    async def _go() -> None:
        await _resend_service().send(
            EmailMessage(
                to="u@example.com",
                template=TEMPLATE_VERIFY_EMAIL,
                context={"token": "t", "name": "U"},
            )
        )

    run(_go())
    (call,) = _FakeAsyncClient.instances[0].calls
    assert str(call["url"]) == "https://api.resend.com/emails"
    headers = call["headers"]
    assert isinstance(headers, dict) and headers["Authorization"] == "Bearer test-key"
    payload = call["json"]
    assert isinstance(payload, dict)
    assert payload["to"] == ["u@example.com"]
    assert payload["from"] == "SRS <noreply@example.com>"
    assert "Verify your email" in str(payload["subject"])


def test_resend_never_raises_on_http_error_or_outage(_fake_http: None) -> None:
    _ = _fake_http

    async def _go() -> None:
        message = EmailMessage(to="u@example.com", template=TEMPLATE_RESET_PASSWORD, context={})
        _FakeAsyncClient.status_code = 500
        await _resend_service().send(message)  # API error: swallowed
        _FakeAsyncClient.explode = True
        await _resend_service().send(message)  # outage: swallowed

    run(_go())  # simply returning proves the port contract


# --- email factory -------------------------------------------------------------------------


def test_email_factory_console_in_dev() -> None:
    get_settings.cache_clear()
    try:
        assert isinstance(get_email_service(), ConsoleEmailService)
    finally:
        get_settings.cache_clear()


def test_email_factory_refuses_console_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="forbidden in production"):
            get_email_service()
    finally:
        get_settings.cache_clear()


def test_email_factory_resend_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
            get_email_service()
    finally:
        get_settings.cache_clear()


def test_email_factory_resend_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        assert isinstance(get_email_service(), ResendEmailService)
    finally:
        get_settings.cache_clear()
