"""Analysis read/delete E2E: GET /api/v1/analysis[/{id}], DELETE /{id}.

HTTP-level contract tests (API_CONTRACT §4.3 + §3, Stage 07): detail shape
(equals the POST payload — write and read paths agree), ownership/IDOR (foreign
ids 404 exactly like missing ones), newest-first list + pagination + sort +
filters, cascade delete, and verified-user gating. Self-contained suite (no
cross-test imports, mirrors test_analysis.py fixtures).
"""

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.main import create_app
from app.models import Analysis, Issue, Requirement, User
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
def crud_app(migrated_db: str) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage07-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def crud_client(crud_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(crud_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage07-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw(tag: str = "staple") -> str:
    return f"correct-horse-{tag}-battery-99"


def _register(client: TestClient, email: str) -> Response:
    return client.post(
        "/api/v1/auth/register",
        json={"name": "Stage Seven", "email": email, "password": _pw()},
    )


def _login(client: TestClient, email: str) -> Response:
    return client.post("/api/v1/auth/login", json={"email": email, "password": _pw()})


async def _verify_user(email: str) -> None:
    """Direct DB write WITHOUT the conftest truncate (see test_auth pattern)."""
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            user = (await session.execute(select(User).where(User.email == email))).scalar_one()
            user.is_verified = True
            await session.commit()
    finally:
        await engine.dispose()


async def _row_counts() -> tuple[int, int, int]:
    """(analyses, requirements, issues) row counts (cascade assertions)."""
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            counts = []
            for model in (Analysis, Requirement, Issue):
                counts.append(
                    (await session.execute(select(func.count()).select_from(model))).scalar_one()
                )
            return counts[0], counts[1], counts[2]
    finally:
        await engine.dispose()


def _login_verified(client: TestClient, tag: str) -> str:
    email = _email(tag)
    assert _register(client, email).status_code == 201
    run(_verify_user(email))
    assert _login(client, email).status_code == 200
    return email


def _create(client: TestClient, text: str, title: str = "T") -> dict[str, object]:
    resp = client.post("/api/v1/analysis", json={"title": title, "text": text})
    assert resp.status_code == 201
    body: dict[str, object] = resp.json()
    return body


CLEAN_TEXT = "The system shall allow login with email and password."
MESSY_TEXT = "The system should support several payment methods quickly, etc."


# --- GET detail ---------------------------------------------------------------


def test_get_owned_detail_matches_post_payload(crud_client: TestClient) -> None:
    _login_verified(crud_client, "detail")
    posted = _create(crud_client, MESSY_TEXT, title="Messy")
    resp = crud_client.get(f"/api/v1/analysis/{posted['id']}")
    assert resp.status_code == 200
    assert resp.json() == posted  # write and read paths agree, byte for byte


def test_get_detail_scores_and_nests_issues(crud_client: TestClient) -> None:
    _login_verified(crud_client, "nested")
    posted = _create(crud_client, MESSY_TEXT)
    body = crud_client.get(f"/api/v1/analysis/{posted['id']}").json()
    assert body["status"] == "analyzed"
    assert body["score"] is not None and body["band"] is not None
    assert body["issues_count"] > 0
    requirement = body["requirements"][0]
    assert requirement["score"] is not None and requirement["severity"] is not None
    assert requirement["issues_count"] == len(requirement["issues"]) > 0
    issue = requirement["issues"][0]
    assert issue["detector_id"] and issue["category"] and issue["phrase"]
    assert issue["reason"] and issue["recommendation"]
    assert requirement["text"][issue["start_offset"] : issue["end_offset"]] == issue["phrase"]


def test_get_missing_and_foreign_ids_404_identically(crud_client: TestClient) -> None:
    _login_verified(crud_client, "owner")
    owned_id = str(_create(crud_client, CLEAN_TEXT)["id"])
    missing = crud_client.get(f"/api/v1/analysis/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "analysis_not_found"

    _login_verified(crud_client, "stranger")  # same client, new session jar
    foreign = crud_client.get(f"/api/v1/analysis/{owned_id}")
    assert foreign.status_code == 404  # IDOR: foreign reads as missing
    assert foreign.json()["error"]["code"] == "analysis_not_found"


def test_get_detail_requires_verified_session(crud_client: TestClient) -> None:
    _login_verified(crud_client, "gated")
    owned_id = str(_create(crud_client, CLEAN_TEXT)["id"])
    crud_client.cookies.clear()
    assert crud_client.get(f"/api/v1/analysis/{owned_id}").status_code == 401
    email = _email("unverified")
    assert _register(crud_client, email).status_code == 201
    assert _login(crud_client, email).status_code == 200  # unverified CAN log in
    resp = crud_client.get(f"/api/v1/analysis/{owned_id}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "email_unverified"


# --- GET list -----------------------------------------------------------------


def test_list_empty_state_is_zeros_not_404(crud_client: TestClient) -> None:
    _login_verified(crud_client, "empty")
    resp = crud_client.get("/api/v1/analysis")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_list_returns_only_owned_newest_first(crud_client: TestClient) -> None:
    owner_email = _login_verified(crud_client, "lister")
    first = _create(crud_client, CLEAN_TEXT, title="First")
    second = _create(crud_client, MESSY_TEXT, title="Second")
    _login_verified(crud_client, "other")
    _create(crud_client, CLEAN_TEXT, title="Stranger")
    assert _login(crud_client, owner_email).status_code == 200  # back to owner
    body = crud_client.get("/api/v1/analysis").json()
    assert body["total"] == 2
    assert [item["title"] for item in body["items"]] == ["Second", "First"]
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]
    summary = body["items"][0]
    assert summary["source_excerpt"]  # summary-only field present…
    assert "requirements" not in summary  # …and requirements omitted


def test_list_pagination_and_sort(crud_client: TestClient) -> None:
    _login_verified(crud_client, "pages")
    for index in range(5):
        text = CLEAN_TEXT if index % 2 == 0 else MESSY_TEXT
        _create(crud_client, text, title=f"Analysis {index}")
    page1 = crud_client.get("/api/v1/analysis?page=1&page_size=2").json()
    assert (page1["page"], page1["page_size"], page1["total"]) == (1, 2, 5)
    assert [i["title"] for i in page1["items"]] == ["Analysis 4", "Analysis 3"]
    page3 = crud_client.get("/api/v1/analysis?page=3&page_size=2").json()
    assert [i["title"] for i in page3["items"]] == ["Analysis 0"]
    assert crud_client.get("/api/v1/analysis?page=9&page_size=2").json()["items"] == []

    by_score = crud_client.get("/api/v1/analysis?sort=score").json()
    scores = [i["score"] for i in by_score["items"]]
    assert scores == sorted(scores) and len(scores) == 5
    by_score_desc = crud_client.get("/api/v1/analysis?sort=-score").json()
    assert [i["score"] for i in by_score_desc["items"]] == sorted(scores, reverse=True)
    oldest = crud_client.get("/api/v1/analysis?sort=created_at").json()
    assert [i["title"] for i in oldest["items"]][0] == "Analysis 0"


def test_list_filters_and_validation(crud_client: TestClient) -> None:
    _login_verified(crud_client, "filters")
    clean = _create(crud_client, CLEAN_TEXT, title="Clean")
    _create(crud_client, MESSY_TEXT, title="Messy")
    assert clean["band"] == "low"
    low_only = crud_client.get("/api/v1/analysis?band=low").json()
    assert [i["title"] for i in low_only["items"]] == ["Clean"]
    assert crud_client.get("/api/v1/analysis?band=very_high").json()["items"] == []
    text_only = crud_client.get("/api/v1/analysis?source_type=text").json()
    assert text_only["total"] == 2
    assert crud_client.get("/api/v1/analysis?source_type=document").json()["total"] == 0
    assert crud_client.get("/api/v1/analysis?future_param=x").status_code == 200

    bad_sort = crud_client.get("/api/v1/analysis?sort=bogus")
    assert bad_sort.status_code == 400
    assert bad_sort.json()["error"]["code"] == "validation_error"
    bad_page = crud_client.get("/api/v1/analysis?page=0")
    assert bad_page.status_code == 400


def test_list_requires_verified_session(crud_client: TestClient) -> None:
    _login_verified(crud_client, "listgated")
    crud_client.cookies.clear()
    assert crud_client.get("/api/v1/analysis").status_code == 401


# --- DELETE -------------------------------------------------------------------


def test_delete_owned_cascades_everything(crud_client: TestClient) -> None:
    _login_verified(crud_client, "deleter")
    posted = _create(crud_client, MESSY_TEXT)
    assert run(_row_counts()) == (1, 1, posted["issues_count"])
    assert posted["issues_count"] > 0
    resp = crud_client.delete(f"/api/v1/analysis/{posted['id']}")
    assert resp.status_code == 204
    assert resp.content == b""
    assert crud_client.get(f"/api/v1/analysis/{posted['id']}").status_code == 404
    assert run(_row_counts()) == (0, 0, 0)  # requirements + issues cascaded


def test_delete_foreign_and_missing_404_without_touching(
    crud_client: TestClient,
) -> None:
    victim_email = _login_verified(crud_client, "victim")
    owned_id = str(_create(crud_client, CLEAN_TEXT)["id"])
    _login_verified(crud_client, "attacker")
    foreign = crud_client.delete(f"/api/v1/analysis/{owned_id}")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "analysis_not_found"
    missing = crud_client.delete(f"/api/v1/analysis/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert _login(crud_client, victim_email).status_code == 200
    assert crud_client.get(f"/api/v1/analysis/{owned_id}").status_code == 200


def test_delete_requires_verified_session_and_honest_origin(
    crud_client: TestClient,
) -> None:
    owner_email = _login_verified(crud_client, "delgated")
    owned_id = str(_create(crud_client, CLEAN_TEXT)["id"])
    crud_client.cookies.clear()
    assert crud_client.delete(f"/api/v1/analysis/{owned_id}").status_code == 401
    assert _login(crud_client, owner_email).status_code == 200
    forged = crud_client.delete(
        f"/api/v1/analysis/{owned_id}", headers={"origin": "https://evil.example.com"}
    )
    assert forged.status_code == 403  # CSRF: cross-origin mutation refused
    assert crud_client.get(f"/api/v1/analysis/{owned_id}").status_code == 200


# --- determinism ---------------------------------------------------------------


def test_repeat_post_is_deterministic_modulo_ids(crud_client: TestClient) -> None:
    _login_verified(crud_client, "determinism")

    def _normalize(body: dict[str, object]) -> object:
        redacted = dict(body)
        for key in ("id", "created_at", "updated_at"):
            redacted.pop(key, None)
        redacted["requirements"] = [
            {k: v for k, v in req.items() if k not in ("id", "analysis_id", "requirement_id")}
            | {
                "issues": [
                    {k: v for k, v in issue.items() if k != "id"}
                    for issue in req["issues"]  # type: ignore[union-attr]
                ]
            }
            for req in body["requirements"]  # type: ignore[union-attr]
        ]
        breakdown = dict(redacted["score_breakdown"])  # type: ignore[arg-type]
        breakdown["deductions"] = [
            {k: v for k, v in d.items() if k != "issue_id"}
            for d in breakdown["deductions"]  # type: ignore[union-attr]
        ]
        redacted["score_breakdown"] = breakdown
        return redacted

    first = _create(crud_client, MESSY_TEXT, title="Same")
    second = _create(crud_client, MESSY_TEXT, title="Same")
    assert first["id"] != second["id"]  # distinct rows…
    assert _normalize(first) == _normalize(second)  # …identical analysis
