"""Health endpoints + uniform error envelope (the project contract, §4.1)."""

from fastapi.testclient import TestClient

from app import __version__


def test_live_returns_ok_shape(client: TestClient) -> None:
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ok",
        "service": "srs-ambiguity-detector",
        "version": __version__,
    }
    assert res.headers["X-Request-ID"]  # request-id middleware active


def test_root_health_alias_matches_live(client: TestClient) -> None:
    """GET /health is a stable infra alias for GET /api/v1/health/live (Stage 00 §6)."""
    alias = client.get("/health")
    live = client.get("/api/v1/health/live")
    assert alias.status_code == 200
    assert alias.json() == live.json()
    assert set(alias.json()) == {"status", "service", "version"}  # no env leakage


def test_ready_reports_dependency_checks(client: TestClient) -> None:
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("ready", "degraded")
    assert "database" in body["checks"]


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "not_found", "message": "Not Found", "details": None}}


def test_security_headers_present(client: TestClient) -> None:
    res = client.get("/api/v1/health/live")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert res.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


def test_openapi_lists_only_real_routes(client: TestClient) -> None:
    res = client.get("/api/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    assert "/api/v1/health/live" in paths
    assert "/api/v1/health/ready" in paths
    assert "DATABASE_URL" not in res.text  # no secrets in schemas
    assert "/health" not in paths  # infra alias excluded from schema
    assert "/" not in paths  # root meta excluded from schema


def test_root_meta_shape(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {
        "service": "srs-ambiguity-detector",
        "version": __version__,
        "docs": "/api/docs",
    }


def test_lifespan_startup_and_shutdown() -> None:
    from app.main import create_app

    with TestClient(create_app()) as lifespan_client:
        res = lifespan_client.get("/api/v1/health/live")
        assert res.status_code == 200
    # Exiting the context runs lifespan shutdown (engine disposal) without errors.
