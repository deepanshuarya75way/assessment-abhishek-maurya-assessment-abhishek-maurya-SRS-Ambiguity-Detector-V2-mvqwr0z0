"""CORS: explicit allowlist, no wildcard methods/headers (no DB)."""

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())
ALLOWED = "http://localhost:3000"


def test_preflight_allowed_origin() -> None:
    res = client.options(
        "/api/v1/health/live",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "GET"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED


def test_preflight_disallowed_origin_gets_no_allow_header() -> None:
    res = client.options(
        "/api/v1/health/live",
        headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in res.headers


def test_actual_request_exposes_request_id_header() -> None:
    res = client.get("/api/v1/health/live", headers={"Origin": ALLOWED})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED
    assert "X-Request-ID" in res.headers["access-control-expose-headers"]
