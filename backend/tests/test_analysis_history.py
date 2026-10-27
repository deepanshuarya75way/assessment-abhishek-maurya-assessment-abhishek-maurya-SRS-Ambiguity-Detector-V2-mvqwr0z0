"""Analysis history reads (API_CONTRACT §4.3, Stage 10).

The history page reads PERSISTED summaries — no recomputation. Covers: the
summary `document` pointer (document vs text, orphan/NULL degradation, no
internal ids/keys leaked) and history search `q` (title + filename matching,
case-insensitivity, LIKE-wildcard safety, blank-as-absent, filter/sort/page
combination, ownership scoping incl. no filename oracle, length cap).
Presenter-level validation units close the file (no HTTP/DB).
"""

import os
import uuid
from collections.abc import Callable, Coroutine, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.v1.presenters import summary_response
from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.main import create_app
from app.models import Document, User
from app.services.analysis import AnalysisSummary, DocumentRef
from tests.conftest import TEST_DATABASE_URL, db_test_session, run

# NOTE: credential literals never sit in `password`-named bindings (S106); the
# _pw() helper builds them so every payload value is a call result, not a literal.


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
def history_app(migrated_db: str, tmp_path: Path) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage10-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    os.environ["STORAGE_LOCAL_DIR"] = str(tmp_path / "uploads")
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def history_client(history_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(history_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage10-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw(tag: str = "staple") -> str:
    return f"correct-horse-{tag}-battery-99"


async def _write(fn: Callable[[AsyncSession], Coroutine[Any, Any, None]]) -> None:
    """Direct-DB mutation WITHOUT truncation (db_test_session would wipe)."""
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            await fn(session)
            await session.commit()
    finally:
        await engine.dispose()


async def _verify_user(email: str) -> None:
    async def _flip(session: AsyncSession) -> None:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        user.is_verified = True

    await _write(_flip)


def _login_verified(client: TestClient, tag: str) -> str:
    email = _email(tag)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"name": "Stage Ten", "email": email, "password": _pw()},
        ).status_code
        == 201
    )
    run(_verify_user(email))
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": _pw()}).status_code
        == 200
    )
    return email


def _post_text(client: TestClient, text: str, title: str = "T") -> dict[str, Any]:
    response = client.post("/api/v1/analysis", json={"title": title, "text": text})
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def _upload_txt(
    client: TestClient, text: str, filename: str = "srs.txt", title: str | None = None
) -> dict[str, Any]:
    data = {"title": title} if title is not None else {}
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": (filename, text.encode(), "text/plain")},
        data=data,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _list(client: TestClient, query: str = "") -> dict[str, Any]:
    response = client.get(f"/api/v1/analysis{query}")
    assert response.status_code == 200, response.text
    page: dict[str, Any] = response.json()
    return page


CLEAN_TEXT = "The system shall allow login with email and password."


class TestSummaryDocumentPointer:
    def test_list_document_analysis_carries_pointer(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _upload_txt(history_client, CLEAN_TEXT, "login-spec.txt", title="Login upload")
        page = _list(history_client)
        assert page["total"] == 1
        item = page["items"][0]
        assert item["source_type"] == "document"
        assert item["document"] == {"filename": "login-spec.txt", "file_type": "txt"}
        assert set(item["document"]) == {"filename", "file_type"}
        assert "storage_path" not in str(page)

    def test_list_text_analysis_has_null_document(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="Pasted")
        item = _list(history_client)["items"][0]
        assert item["source_type"] == "text"
        assert item["document"] is None

    def test_list_preserves_existing_shape(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="Shape")
        item = _list(history_client)["items"][0]
        assert set(item) == {
            "id",
            "title",
            "status",
            "source_type",
            "document",
            "source_excerpt",
            "score",
            "band",
            "requirements_count",
            "issues_count",
            "created_at",
            "updated_at",
        }

    def test_orphaned_pointer_reads_as_null(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        body = _upload_txt(history_client, CLEAN_TEXT, "doomed.txt")
        document_id = body["document"]["id"]

        async def _purge_document(session: AsyncSession) -> None:
            await session.execute(delete(Document).where(Document.id == uuid.UUID(document_id)))

        run(_write(_purge_document))
        item = _list(history_client)["items"][0]
        assert item["document"] is None

    def test_null_file_type_degrades_to_null(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        body = _upload_txt(history_client, CLEAN_TEXT, "untyped.txt")
        document_id = body["document"]["id"]

        async def _unverify(session: AsyncSession) -> None:
            await session.execute(
                update(Document).where(Document.id == uuid.UUID(document_id)).values(file_type=None)
            )

        run(_write(_unverify))
        item = _list(history_client)["items"][0]
        assert item["document"] is None


class TestHistorySearch:
    def test_q_matches_title_case_insensitively(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="Alpha Login SRS")
        _post_text(history_client, CLEAN_TEXT, title="Beta Payments")
        page = _list(history_client, "?q=alpha")
        assert page["total"] == 1
        assert [item["title"] for item in page["items"]] == ["Alpha Login SRS"]
        assert _list(history_client, "?q=ALPHA")["total"] == 1

    def test_q_matches_document_filename(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _upload_txt(history_client, CLEAN_TEXT, "acme-contract.txt", title="Q3 Report")
        _post_text(history_client, CLEAN_TEXT, title="Unrelated paste")
        page = _list(history_client, "?q=acme")
        assert page["total"] == 1
        assert page["items"][0]["title"] == "Q3 Report"
        assert _list(history_client, "?q=paste")["total"] == 1

    def test_q_no_match_is_empty_not_404(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="Something")
        page = _list(history_client, "?q=zzz-no-such-thing")
        assert page["items"] == []
        assert page["total"] == 0

    def test_q_blank_is_absent(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="Something")
        assert _list(history_client, "?q=%20%20")["total"] == 1
        assert _list(history_client, "?q=")["total"] == 1

    def test_q_escapes_like_wildcards(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="100% coverage_sure")
        _post_text(history_client, CLEAN_TEXT, title="Just a plain title")
        assert _list(history_client, "?q=100%25")["total"] == 1  # literal %
        underscore = _list(history_client, "?q=coverage_sure")
        assert underscore["total"] == 1  # literal _, not single-char wildcard
        assert _list(history_client, "?q=%25")["total"] == 1  # bare % matches one row, not all
        assert _list(history_client, "?q=plain")["total"] == 1

    def test_q_combines_with_filters_sort_paging(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="alpha one")
        _post_text(history_client, CLEAN_TEXT, title="alpha two")
        _post_text(history_client, CLEAN_TEXT, title="beta three")
        page1 = _list(history_client, "?q=alpha&page=1&page_size=1&sort=-created_at")
        page2 = _list(history_client, "?q=alpha&page=2&page_size=1&sort=-created_at")
        assert page1["total"] == 2 == page2["total"]  # total honors q on every page
        assert page1["items"][0]["id"] != page2["items"][0]["id"]
        assert {page1["items"][0]["title"], page2["items"][0]["title"]} == {
            "alpha one",
            "alpha two",
        }
        assert _list(history_client, "?q=alpha&band=low")["total"] == 2
        assert _list(history_client, "?q=alpha&band=high")["total"] == 0
        assert _list(history_client, "?q=alpha&source_type=text")["total"] == 2
        assert _list(history_client, "?q=alpha&source_type=document")["total"] == 0

    def test_q_is_ownership_scoped(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="secret-acme-plans")
        _upload_txt(history_client, CLEAN_TEXT, "secret-file.txt", title="Hidden upload")
        history_client.cookies.clear()
        _login_verified(history_client, "b")
        response = history_client.get("/api/v1/analysis?q=secret")
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert "secret" not in response.text  # no filename/title oracle via search

    def test_q_too_long_is_400(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        response = history_client.get(f"/api/v1/analysis?q={'x' * 201}")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "validation_error"

    def test_unknown_params_still_ignored(self, history_client: TestClient) -> None:
        _login_verified(history_client, "a")
        _post_text(history_client, CLEAN_TEXT, title="Something")
        page = _list(history_client, "?category=whatever&severity=high")
        assert page["total"] == 1  # future params stay forward-compatible no-ops


class TestSummaryPresenterValidation:
    def _summary(self, **overrides: Any) -> AnalysisSummary:
        params: dict[str, Any] = {
            "id": uuid.uuid4(),
            "title": "T",
            "status": "analyzed",
            "source_type": "text",
            "source_excerpt": "excerpt",
            "score": 100,
            "band": "low",
            "requirements_count": 1,
            "issues_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        params.update(overrides)
        return AnalysisSummary(**params)

    def test_summary_pointer_maps(self) -> None:
        response = summary_response(
            self._summary(
                source_type="document",
                document=DocumentRef(filename="a.pdf", file_type="pdf"),
            )
        )
        assert response.document is not None
        assert response.document.filename == "a.pdf"
        assert response.document.file_type == "pdf"

    def test_summary_rejects_unexpected_file_type(self) -> None:
        with pytest.raises(ValueError, match="unexpected file type"):
            summary_response(self._summary(document=DocumentRef(filename="a", file_type="exe")))

    def test_summary_rejects_unexpected_status(self) -> None:
        with pytest.raises(ValueError, match="unexpected analysis status"):
            summary_response(self._summary(status="nope"))
