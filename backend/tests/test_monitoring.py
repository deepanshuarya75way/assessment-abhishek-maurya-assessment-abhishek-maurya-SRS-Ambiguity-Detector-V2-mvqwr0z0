"""Stage 24 monitoring/privacy regression tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import monitoring
from app.exceptions import InternalError, NotFoundError
from app.main import create_app


def test_sentry_before_send_scrubs_request_exception_and_context() -> None:
    event = {
        "request": {
            "url": "https://api.example.test/api/v1/auth/reset-password?token=reset-secret",
            "query_string": "token=reset-secret",
            "headers": {
                "authorization": "Bearer access-secret",
                "cookie": "refresh_token=refresh-secret",
                "x-request-id": "trace-123",
            },
            "data": {
                "password": "hunter2",
                "text": "FR-001 The raw SRS shall never be copied here.",
                "api" + "_key": "example-provider-key",
            },
        },
        "extra": {
            "csrf_token": "csrf-secret",
            "prompt": "AI prompt with requirement text",
            "safe_count": 3,
        },
        "exception": {"values": [{"type": "RuntimeError", "value": "raw user content"}]},
    }

    scrubbed = monitoring.before_send(event, {})
    assert scrubbed is not None
    text = str(scrubbed)
    assert "reset-secret" not in text
    assert "access-secret" not in text
    assert "refresh-secret" not in text
    assert "hunter2" not in text
    assert "example-provider-key" not in text
    assert "AI prompt" not in text
    assert "raw user content" not in text
    assert "FR-001 The raw SRS" not in text
    assert scrubbed["request"]["url"] == "https://api.example.test/api/v1/auth/reset-password"
    assert scrubbed["exception"]["values"][0]["value"] == "details redacted"


def _client_with_routes(app: FastAPI) -> TestClient:
    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("raw SRS text should not reach the client")

    @app.get("/expected")
    async def expected() -> None:
        raise NotFoundError("analysis")

    @app.get("/internal")
    async def internal() -> None:
        raise InternalError("Data cleanup failed. Please try again.")

    return TestClient(app, raise_server_exceptions=False)


def test_unexpected_exception_returns_safe_envelope_and_is_captured(monkeypatch) -> None:
    captured: list[tuple[type[BaseException], str | None, dict[str, object] | None]] = []

    def fake_capture(exc: BaseException, *, request_id: str | None = None, context=None) -> None:
        captured.append((type(exc), request_id, context))

    monkeypatch.setattr("app.main.capture_exception", fake_capture)
    client = _client_with_routes(create_app())

    res = client.get("/boom", headers={"X-Request-ID": "trace-123"})

    assert res.status_code == 500
    assert res.headers["X-Request-ID"] == "trace-123"
    assert res.json() == {
        "error": {"code": "internal_error", "message": "Internal server error.", "details": None}
    }
    assert "raw SRS" not in res.text
    assert captured == [
        (
            RuntimeError,
            "trace-123",
            {"error_code": "internal_error", "exception_class": "RuntimeError"},
        )
    ]


def test_expected_business_errors_are_not_captured(monkeypatch) -> None:
    captured: list[BaseException] = []

    def fake_capture(exc: BaseException, *, request_id: str | None = None, context=None) -> None:
        captured.append(exc)

    monkeypatch.setattr("app.main.capture_exception", fake_capture)
    client = _client_with_routes(create_app())

    res = client.get("/expected")

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "analysis_not_found"
    assert captured == []


def test_500_app_errors_are_captured_without_sensitive_details(monkeypatch) -> None:
    captured: list[tuple[type[BaseException], dict[str, object] | None]] = []

    def fake_capture(exc: BaseException, *, request_id: str | None = None, context=None) -> None:
        _ = request_id
        captured.append((type(exc), context))

    monkeypatch.setattr("app.main.capture_exception", fake_capture)
    client = _client_with_routes(create_app())

    res = client.get("/internal")

    assert res.status_code == 500
    assert res.json()["error"] == {
        "code": "internal_error",
        "message": "Data cleanup failed. Please try again.",
        "details": None,
    }
    assert captured == [
        (InternalError, {"error_code": "internal_error", "exception_class": "InternalError"})
    ]


def test_capture_helpers_never_break_application(monkeypatch) -> None:
    def failing_capture(exc: BaseException) -> None:
        _ = exc
        raise RuntimeError("sentry down")

    monkeypatch.setattr(monitoring, "_capture_exception", failing_capture)
    monitoring.capture_exception(RuntimeError("boom"), request_id="trace-123")


def test_monitoring_message_context_is_allowlisted(monkeypatch) -> None:
    seen: list[str] = []

    def fake_message(message: str, *, level: str = "info") -> str:
        seen.append(f"{level}:{message}")
        return "event-id"

    monkeypatch.setattr(monitoring, "_capture_message", fake_message)
    monitoring.capture_message(
        "provider failed api_key=example-provider-key",
        level="warning",
        context={"ai_provider": "openai", "prompt": "raw requirement text"},
    )

    assert seen == ["warning:provider failed api_key=***REDACTED***"]
