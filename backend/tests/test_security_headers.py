"""Production posture: security headers + OpenAPI gating (SECURITY_SPEC §8).

Non-prod asserts the always-on baseline; production asserts HSTS, framing
denial, and the disabled docs surface. Error responses must carry the same
headers (the middleware wraps exception envelopes too).
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

_BASELINE = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
_PROD_ONLY = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


@pytest.fixture
def prod_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """App booted as production (mirrors the Stage 04 prod-cookie pattern)."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-only-dummy-key")
    os.environ["JWT_SECRET"] = "stage20-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_non_production_omits_transport_and_framing_headers(client: TestClient) -> None:
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    for header in _PROD_ONLY:
        assert header not in res.headers


def test_production_security_headers_present(prod_client: TestClient) -> None:
    res = prod_client.get("/api/v1/health/live")
    assert res.status_code == 200
    for header, value in {**_BASELINE, **_PROD_ONLY}.items():
        assert res.headers[header] == value


def test_production_error_responses_carry_security_headers(prod_client: TestClient) -> None:
    res = prod_client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"
    for header, value in {**_BASELINE, **_PROD_ONLY}.items():
        assert res.headers[header] == value


def test_openapi_docs_disabled_in_production(prod_client: TestClient) -> None:
    for path in ("/api/docs", "/api/redoc", "/api/openapi.json"):
        assert prod_client.get(path).status_code == 404


def test_openapi_docs_enabled_outside_production(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/redoc").status_code == 200
