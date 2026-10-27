"""Error envelope: AppError mapping, sanitization, validation, unhandled (no DB).

Canonical shape (API_CONTRACT §2): {"error": {code, message, details}}.
"""

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.main import create_app


def _client() -> TestClient:
    app: FastAPI = create_app()

    @app.get("/boom/not-found")
    async def not_found() -> None:
        raise NotFoundError("analysis")

    @app.get("/boom/conflict")
    async def conflict() -> None:
        raise ConflictError("email_taken", "That email is already registered.")

    @app.get("/boom/unauthorized")
    async def unauthorized() -> None:
        raise UnauthorizedError()

    @app.get("/boom/forbidden")
    async def forbidden() -> None:
        raise ForbiddenError()

    @app.get("/boom/db")
    async def db() -> None:
        raise SQLAlchemyError("SELECT * FROM users -- postgres://u:p@h/db")

    @app.get("/boom/unhandled")
    async def unhandled() -> None:
        raise RuntimeError("kaboom")

    @app.get("/boom/validated")
    async def validated(q: int = Query(...)) -> dict[str, int]:
        return {"q": q}

    return TestClient(app, raise_server_exceptions=False)


client = _client()


def test_not_found_envelope() -> None:
    res = client.get("/boom/not-found")
    assert res.status_code == 404
    assert res.json() == {
        "error": {
            "code": "analysis_not_found",
            "message": "The requested resource was not found.",
            "details": None,
        }
    }


def test_conflict_envelope() -> None:
    res = client.get("/boom/conflict")
    assert res.status_code == 409
    assert res.json() == {
        "error": {
            "code": "email_taken",
            "message": "That email is already registered.",
            "details": None,
        }
    }


def test_unauthorized_envelope() -> None:
    res = client.get("/boom/unauthorized")
    assert res.status_code == 401
    assert res.json() == {
        "error": {
            "code": "unauthenticated",
            "message": "Authentication required.",
            "details": None,
        }
    }


def test_forbidden_envelope() -> None:
    res = client.get("/boom/forbidden")
    assert res.status_code == 403
    assert res.json() == {
        "error": {
            "code": "forbidden",
            "message": "You do not have access to this resource.",
            "details": None,
        }
    }


def test_sqlalchemy_error_sanitized() -> None:
    res = client.get("/boom/db")
    assert res.status_code == 500
    assert res.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error.",
            "details": None,
        }
    }
    assert "postgres://" not in res.text and "SELECT" not in res.text


def test_unhandled_error_sanitized() -> None:
    res = client.get("/boom/unhandled")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "internal_error"
    assert "kaboom" not in res.text


def test_validation_error_envelope() -> None:
    res = client.get("/boom/validated", params={"q": "not-an-int"})
    assert res.status_code == 400
    body = res.json()["error"]
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed."
    assert isinstance(body["details"], list) and len(body["details"]) == 1
    assert body["details"][0]["loc"] == ["query", "q"]
    assert "integer" in body["details"][0]["msg"]
