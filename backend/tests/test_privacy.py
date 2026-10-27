"""Stage 23 privacy/data lifecycle tests.

Covers account deletion storage cleanup, owner-scoped export safety, history
purge/retention, and failure/retry semantics against real PostgreSQL.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.core.security import create_document_download_token, utcnow
from app.email.base import EmailMessage, EmailService
from app.main import create_app
from app.models import (
    AICredential,
    Analysis,
    Document,
    EmailVerificationToken,
    Issue,
    PasswordResetToken,
    RefreshToken,
    Requirement,
    User,
    UserPreference,
)
from app.services.privacy import enforce_configured_retention
from tests.conftest import TEST_DATABASE_URL, db_test_session, run


class FakeEmailService(EmailService):
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


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
            pass

    run(_truncate())
    yield
    run(_truncate())


@pytest.fixture()
def privacy_app(migrated_db: str, tmp_path: Path) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage23-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    os.environ["STORAGE_LOCAL_DIR"] = str(tmp_path / "uploads")
    get_settings.cache_clear()
    app = create_app()
    app.state.email_service = FakeEmailService()
    return app


@pytest.fixture()
def privacy_client(privacy_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(privacy_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage23-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw(tag: str = "main") -> str:
    return f"correct-horse-stage23-{tag}-battery-99"


def _register(client: TestClient, email: str) -> Response:
    return client.post(
        "/api/v1/auth/register",
        json={"name": "Privacy User", "email": email, "password": _pw()},
    )


def _login(client: TestClient, email: str) -> Response:
    return client.post("/api/v1/auth/login", json={"email": email, "password": _pw()})


async def _verify_user(email: str) -> uuid.UUID:
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            user = (await session.execute(select(User).where(User.email == email))).scalar_one()
            user.is_verified = True
            user_id = user.id
            await session.commit()
            return user_id
    finally:
        await engine.dispose()


def _login_verified(client: TestClient, tag: str) -> tuple[str, uuid.UUID]:
    email = _email(tag)
    assert _register(client, email).status_code == 201
    user_id = run(_verify_user(email))
    assert _login(client, email).status_code == 200
    return email, user_id


def _upload_txt(client: TestClient, text: bytes, filename: str = "spec.txt") -> dict[str, Any]:
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": (filename, text, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _storage_paths_for(owner_id: uuid.UUID) -> list[str]:
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            rows = await session.execute(
                select(Document.storage_path).where(Document.owner_id == owner_id)
            )
            return list(rows.scalars().all())
    finally:
        await engine.dispose()


async def _make_rows_old(owner_id: uuid.UUID, *, days: int) -> None:
    cutoff = utcnow() - timedelta(days=days)
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            await session.execute(
                update(Analysis).where(Analysis.owner_id == owner_id).values(created_at=cutoff)
            )
            await session.execute(
                update(Document).where(Document.owner_id == owner_id).values(created_at=cutoff)
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _insert_provider_ciphertext(owner_id: uuid.UUID) -> None:
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            session.add(
                AICredential(
                    owner_id=owner_id,
                    provider="openai",
                    label="Work key",
                    encrypted_api_key="v1:encrypted-ciphertext-never-exported",
                    key_version=1,
                    key_fingerprint="abcdef1234567890",
                    last4="7890",
                    is_enabled=True,
                    is_default=True,
                    fallback_rank=0,
                    last_test_status="ok",
                    last_tested_at=utcnow(),
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _row_counts(owner_id: uuid.UUID) -> dict[str, int]:
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            models = {
                "users": User,
                "analyses": Analysis,
                "requirements": Requirement,
                "issues": Issue,
                "documents": Document,
                "ai_provider_credentials": AICredential,
                "refresh_tokens": RefreshToken,
                "email_verification_tokens": EmailVerificationToken,
                "password_reset_tokens": PasswordResetToken,
                "user_preferences": UserPreference,
            }
            counts: dict[str, int] = {}
            for name, model in models.items():
                column = model.id if name == "users" else model.owner_id
                counts[name] = (
                    await session.execute(
                        select(func.count()).select_from(model).where(column == owner_id)
                    )
                ).scalar_one()
            return counts
    finally:
        await engine.dispose()


def _storage_root() -> Path:
    return Path(os.environ["STORAGE_LOCAL_DIR"])


def test_privacy_settings_are_authenticated_csrf_guarded_and_persisted(
    privacy_client: TestClient,
) -> None:
    assert privacy_client.get("/api/v1/settings/privacy").status_code == 401
    _email_addr, _user_id = _login_verified(privacy_client, "settings")
    assert privacy_client.get("/api/v1/settings/privacy").json() == {"history_retention_days": None}
    evil = privacy_client.patch(
        "/api/v1/settings/privacy",
        json={"history_retention_days": 30},
        headers={"Origin": "https://evil.test"},
    )
    assert evil.status_code == 403
    saved = privacy_client.patch("/api/v1/settings/privacy", json={"history_retention_days": 30})
    assert saved.status_code == 200
    assert saved.json() == {"history_retention_days": 30}
    assert privacy_client.get("/api/v1/settings/privacy").json() == {"history_retention_days": 30}


def test_account_deletion_purges_rows_tokens_credentials_and_owned_storage(
    privacy_client: TestClient,
) -> None:
    email, owner_id = _login_verified(privacy_client, "delete")
    _upload_txt(privacy_client, b"FR-001: The system shall respond quickly.\n")
    _upload_txt(privacy_client, b"FR-002: The system shall be user-friendly.\n", "second.txt")
    privacy_client.patch("/api/v1/settings/privacy", json={"history_retention_days": 90})
    privacy_client.post("/api/v1/auth/forgot-password", json={"email": email})
    run(_insert_provider_ciphertext(owner_id))
    paths = run(_storage_paths_for(owner_id))
    assert len(paths) == 2
    for path in paths:
        assert (_storage_root() / path).exists()

    resp = privacy_client.request("DELETE", "/api/v1/auth/account", json={"confirmation": "DELETE"})
    assert resp.status_code == 204
    assert all(not (_storage_root() / path).exists() for path in paths)
    assert run(_row_counts(owner_id)) == {
        "users": 0,
        "analyses": 0,
        "requirements": 0,
        "issues": 0,
        "documents": 0,
        "ai_provider_credentials": 0,
        "refresh_tokens": 0,
        "email_verification_tokens": 0,
        "password_reset_tokens": 0,
        "user_preferences": 0,
    }
    assert privacy_client.get("/api/v1/auth/me").status_code == 401
    refresh = privacy_client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 400
    assert refresh.json()["error"]["code"] == "invalid_token"
    assert _login(privacy_client, email).status_code == 401


def test_account_deletion_storage_failure_aborts_and_retry_is_safe(
    privacy_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email, owner_id = _login_verified(privacy_client, "storagefail")
    _upload_txt(privacy_client, b"FR-001: Keep this if storage fails.\n")
    paths = run(_storage_paths_for(owner_id))

    class FailingStorage:
        def delete(self, key: str) -> None:
            _ = key
            raise OSError("simulated storage outage")

        def store_file(self, key: str, src: Path) -> None:  # pragma: no cover - not used
            raise AssertionError("not used")

        def read_bytes(self, key: str) -> bytes:  # pragma: no cover - not used
            raise AssertionError("not used")

    monkeypatch.setattr("app.services.privacy.get_storage_backend", lambda: FailingStorage())
    failed = privacy_client.request(
        "DELETE", "/api/v1/auth/account", json={"confirmation": "DELETE"}
    )
    assert failed.status_code == 500
    assert run(_row_counts(owner_id))["users"] == 1
    assert (_storage_root() / paths[0]).exists()

    monkeypatch.undo()
    assert _login(privacy_client, email).status_code == 200
    retried = privacy_client.request(
        "DELETE", "/api/v1/auth/account", json={"confirmation": "DELETE"}
    )
    assert retried.status_code == 204
    assert not (_storage_root() / paths[0]).exists()


def test_privacy_export_is_owner_scoped_and_excludes_secrets(
    privacy_client: TestClient,
) -> None:
    _other_email, other_id = _login_verified(privacy_client, "other")
    other_upload = _upload_txt(privacy_client, b"FR-001: Other user's document.\n")
    other_doc = other_upload["document"]["id"]
    privacy_client.cookies.clear()

    email, owner_id = _login_verified(privacy_client, "export")
    _ = email
    _upload_txt(privacy_client, b"FR-001: The system shall process requests quickly.\n")
    privacy_client.patch("/api/v1/settings/privacy", json={"history_retention_days": 120})
    run(_insert_provider_ciphertext(owner_id))

    ticket = privacy_client.post("/api/v1/privacy/export")
    assert ticket.status_code == 202
    body = ticket.json()
    exported = privacy_client.get(body["download_url"])
    assert exported.status_code == 200
    payload = exported.json()
    rendered = exported.text
    assert payload["profile"]["email"] == email
    assert payload["privacy_settings"] == {"history_retention_days": 120}
    assert payload["analyses"] and payload["documents"]
    assert payload["ai_provider_credentials"] == [
        {
            **payload["ai_provider_credentials"][0],
            "provider": "openai",
            "label": "Work key",
        }
    ]
    forbidden = [
        "password_hash",
        "token_hash",
        "refresh_tokens",
        "email_verification_tokens",
        "password_reset_tokens",
        "encrypted_api_key",
        "encrypted-ciphertext-never-exported",
        "key_fingerprint",
        "last4",
        "storage_path",
        other_doc,
        str(other_id),
    ]
    for needle in forbidden:
        assert needle not in rendered

    export_id = body["export_id"]
    privacy_client.cookies.clear()
    _login_verified(privacy_client, "intruder")
    cross = privacy_client.get(f"/api/v1/privacy/export/{export_id}")
    assert cross.status_code == 400
    assert cross.json()["error"]["code"] == "invalid_token"


def test_purge_history_deletes_only_eligible_owned_analyses_and_storage(
    privacy_client: TestClient,
) -> None:
    _other_email, other_id = _login_verified(privacy_client, "purge-other")
    _upload_txt(privacy_client, b"FR-001: Other old document.\n", "other.txt")
    run(_make_rows_old(other_id, days=90))
    other_paths = run(_storage_paths_for(other_id))
    privacy_client.cookies.clear()

    _email_addr, owner_id = _login_verified(privacy_client, "purge")
    old = _upload_txt(privacy_client, b"FR-001: Old document should go.\n", "old.txt")
    old_doc = old["document"]["id"]
    run(_make_rows_old(owner_id, days=90))
    old_paths = run(_storage_paths_for(owner_id))
    fresh = _upload_txt(privacy_client, b"FR-002: Fresh document should stay.\n", "fresh.txt")
    fresh_doc = fresh["document"]["id"]

    purged = privacy_client.post("/api/v1/privacy/purge-history", json={"older_than_days": 30})
    assert purged.status_code == 200
    assert purged.json() == {"deleted_analyses": 1, "deleted_documents": 1}
    assert not (_storage_root() / old_paths[0]).exists()
    assert all((_storage_root() / path).exists() for path in other_paths)

    docs = privacy_client.get("/api/v1/documents").json()
    ids = {item["id"] for item in docs["items"]}
    assert old_doc not in ids
    assert fresh_doc in ids

    privacy_client.cookies.clear()
    assert _login(privacy_client, _other_email).status_code == 200
    assert privacy_client.get("/api/v1/documents").json()["total"] == 1


def test_configured_retention_service_is_rerunnable_and_safe(privacy_client: TestClient) -> None:
    _email_addr, owner_id = _login_verified(privacy_client, "retention")
    _upload_txt(privacy_client, b"FR-001: Old retained document.\n")
    run(_make_rows_old(owner_id, days=90))
    privacy_client.patch("/api/v1/settings/privacy", json={"history_retention_days": 30})
    paths = run(_storage_paths_for(owner_id))

    async def _run_retention() -> tuple[int, int, int]:
        engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
        try:
            async with AsyncSession(engine) as session:
                result = await enforce_configured_retention(session)
                return result.users_scanned, result.deleted_analyses, result.deleted_documents
        finally:
            await engine.dispose()

    assert run(_run_retention()) == (1, 1, 1)
    assert not (_storage_root() / paths[0]).exists()
    assert run(_run_retention()) == (1, 0, 0)


def test_deleted_document_download_token_cannot_revive_after_account_delete(
    privacy_client: TestClient,
) -> None:
    _email_addr, owner_id = _login_verified(privacy_client, "download-token")
    upload = _upload_txt(privacy_client, b"FR-001: Download token dies with account.\n")
    document_id = uuid.UUID(upload["document"]["id"])
    token = create_document_download_token(owner_id, document_id, 15)
    assert (
        privacy_client.get(f"/api/v1/documents/{document_id}/download?token={token}").status_code
        == 200
    )
    deleted = privacy_client.request(
        "DELETE", "/api/v1/auth/account", json={"confirmation": "DELETE"}
    )
    assert deleted.status_code == 204
    after = privacy_client.get(f"/api/v1/documents/{document_id}/download?token={token}")
    assert after.status_code == 404
    assert after.json()["error"]["code"] == "document_not_found"
