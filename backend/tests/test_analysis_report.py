"""Analysis report reads (API_CONTRACT §4.3, Stage 09).

The result page reads PERSISTED details — no recomputation, no re-analysis.
Covers: the `document` source pointer (document vs text, upload/GET parity,
no internal ids/keys leaked), legacy/failed statuses reading back honestly,
score-breakdown internal consistency, clean-analysis shape, position order,
and IDOR on document-bearing analyses. Presenter-level validation units close
the file (no HTTP/DB).
"""

import math
import os
import uuid
from collections.abc import Callable, Coroutine, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.v1.presenters import detail_response
from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.main import create_app
from app.models import Analysis, Document, Issue, Requirement, User
from app.services.analysis import AnalysisDetail, DocumentRef
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
def report_app(migrated_db: str, tmp_path: Path) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage09-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    os.environ["STORAGE_LOCAL_DIR"] = str(tmp_path / "uploads")
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def report_client(report_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(report_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage09-{tag}-{uuid.uuid4().hex[:8]}@example.com"


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
            json={"name": "Stage Nine", "email": email, "password": _pw()},
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


def _upload_txt(client: TestClient, text: str, filename: str = "srs.txt") -> dict[str, Any]:
    response = client.post(
        "/api/v1/documents/upload",
        files={"files": (filename, text.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


class TestDocumentSourcePointer:
    TEXT = "FR-001: The system shall allow login.\nFR-002: The service must be available always.\n"

    def test_get_document_analysis_carries_source_ref(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        body = _upload_txt(report_client, self.TEXT, "login-spec.txt")
        detail = report_client.get(f"/api/v1/analysis/{body['analysis']['id']}").json()
        assert detail["source_type"] == "document"
        assert detail["document"] == {"filename": "login-spec.txt", "file_type": "txt"}
        # No ids, keys, or binary-adjacent fields leak through the pointer.
        assert set(detail["document"]) == {"filename", "file_type"}
        assert "storage_path" not in str(detail)

    def test_get_text_analysis_has_null_document(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        posted = _post_text(report_client, self.TEXT)
        assert posted["document"] is None
        detail = report_client.get(f"/api/v1/analysis/{posted['id']}").json()
        assert detail["source_type"] == "text"
        assert detail["document"] is None

    def test_upload_post_and_get_details_agree(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        body = _upload_txt(report_client, self.TEXT)
        fetched = report_client.get(f"/api/v1/analysis/{body['analysis']['id']}").json()
        assert fetched == body["analysis"]  # write and read paths agree, byte for byte

    def test_foreign_analysis_hides_everything(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        body = _upload_txt(report_client, self.TEXT, "secret-srs.txt")
        report_client.cookies.clear()
        _login_verified(report_client, "b")
        response = report_client.get(f"/api/v1/analysis/{body['analysis']['id']}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_not_found"
        assert "secret-srs" not in response.text  # no filename oracle

    def test_orphaned_pointer_reads_as_null(self, report_client: TestClient) -> None:
        """SET NULL (schema-level doc purge) degrades to `document: null`."""
        _login_verified(report_client, "a")
        body = _upload_txt(report_client, self.TEXT)
        analysis_id, document_id = body["analysis"]["id"], body["document"]["id"]

        async def _purge_document(session: AsyncSession) -> None:
            await session.execute(delete(Document).where(Document.id == uuid.UUID(document_id)))

        run(_write(_purge_document))
        detail = report_client.get(f"/api/v1/analysis/{analysis_id}").json()
        assert detail["document"] is None


class TestLegacyAndFailedStatuses:
    TEXT = "FR-001: The system should respond quickly.\n"

    def test_failed_status_reads_back_honestly(self, report_client: TestClient) -> None:
        """Nothing WRITES failed rows yet — but the read path tolerates them
        (the report UI renders a failure state instead of fabricated scores)."""
        _login_verified(report_client, "a")
        analysis_id = _post_text(report_client, self.TEXT)["id"]

        async def _fail(session: AsyncSession) -> None:
            row = (
                await session.execute(select(Analysis).where(Analysis.id == uuid.UUID(analysis_id)))
            ).scalar_one()
            row.status = "failed"
            row.score = None
            row.band = None
            row.health = None
            row.score_breakdown = {}

        run(_write(_fail))
        response = report_client.get(f"/api/v1/analysis/{analysis_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["status"] == "failed"
        assert detail["score"] is None and detail["band"] is None
        assert detail["health"] is None and detail["score_breakdown"] == {}

    def test_segmented_legacy_row_reads_back_unscored(self, report_client: TestClient) -> None:
        """Pre-Stage-07 rows: requirements WITHOUT scores or issues."""
        _login_verified(report_client, "a")
        analysis_id = _post_text(report_client, self.TEXT)["id"]

        async def _revert(session: AsyncSession) -> None:
            await session.execute(delete(Issue).where(Issue.analysis_id == uuid.UUID(analysis_id)))
            for req in (
                await session.execute(
                    select(Requirement).where(Requirement.analysis_id == uuid.UUID(analysis_id))
                )
            ).scalars():
                req.score = None
                req.severity = None
                req.issues_count = 0
            row = (
                await session.execute(select(Analysis).where(Analysis.id == uuid.UUID(analysis_id)))
            ).scalar_one()
            row.status = "segmented"
            row.score = None
            row.band = None
            row.health = None
            row.score_breakdown = {}
            row.issues_count = 0

        run(_write(_revert))
        response = report_client.get(f"/api/v1/analysis/{analysis_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["status"] == "segmented"
        assert detail["issues_count"] == 0
        assert len(detail["requirements"]) == 1
        req = detail["requirements"][0]
        assert req["score"] is None and req["severity"] is None and req["issues"] == []
        assert req["identifier"] == "FR-001"


class TestScoreConsistency:
    TEXT = (
        "FR-001: The system should respond quickly to user requests.\n"
        "FR-002: The service must be available always.\n"
    )

    def test_breakdown_links_every_point_to_an_issue(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        detail = _post_text(report_client, self.TEXT)
        breakdown = detail["score_breakdown"]
        nested_ids = {issue["id"] for req in detail["requirements"] for issue in req["issues"]}
        assert breakdown["base"] == 100
        assert {d["issue_id"] for d in breakdown["deductions"]} == nested_ids
        assert sum(breakdown["counts"].values()) == detail["issues_count"] == len(nested_ids)

    def test_overall_is_mean_of_requirements_half_up(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        detail = _post_text(report_client, self.TEXT)
        scores = [req["score"] for req in detail["requirements"]]
        assert detail["score"] == math.floor(sum(scores) / len(scores) + 0.5)

    def test_band_edges(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        detail = _post_text(report_client, self.TEXT)
        score, band = detail["score"], detail["band"]
        expected = (
            "low"
            if score >= 80
            else "moderate"
            if score >= 60
            else "high"
            if score >= 40
            else "very_high"
        )
        assert band == expected

    def test_clean_analysis_shape(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        detail = _post_text(report_client, "FR-001: The system shall allow login.\n")
        assert detail["issues_count"] == 0
        assert detail["score"] == 100 and detail["band"] == "low"
        assert detail["score_breakdown"]["deductions"] == []
        assert set(detail["health"].values()) == {100}
        req = detail["requirements"][0]
        assert (req["score"], req["severity"], req["issues"]) == (100, None, [])

    def test_requirements_follow_input_order(self, report_client: TestClient) -> None:
        _login_verified(report_client, "a")
        detail = _post_text(
            report_client,
            "FR-003: Third requirement here.\nFR-001: First requirement here.\n",
        )
        assert [(r["position"], r["identifier"]) for r in detail["requirements"]] == [
            (0, "FR-003"),
            (1, "FR-001"),
        ]


class TestPresenterValidationUnits:
    """No HTTP/DB: unknown vocabularies 500 via ValueError, never serialize."""

    def _detail(self, **overrides: Any) -> AnalysisDetail:
        now = datetime.now(UTC)
        params: dict[str, Any] = {
            "id": uuid.uuid4(),
            "title": "T",
            "status": "analyzed",
            "source_type": "text",
            "score": 100,
            "band": "low",
            "score_breakdown": {"base": 100, "deductions": [], "counts": {}},
            "health": None,
            "requirements_count": 0,
            "issues_count": 0,
            "created_at": now,
            "updated_at": now,
            "requirements": (),
            "document": None,
        }
        params.update(overrides)
        return AnalysisDetail(**params)

    def test_unknown_status_rejected(self) -> None:
        with pytest.raises(ValueError, match="unexpected analysis status"):
            detail_response(self._detail(status="processing"))

    def test_unknown_file_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="unexpected file type"):
            detail_response(
                self._detail(
                    source_type="document",
                    document=DocumentRef(filename="s.odt", file_type="odt"),
                )
            )

    def test_failed_status_passes_through(self) -> None:
        response = detail_response(self._detail(status="failed", score=None, band=None))
        assert response.status == "failed"
