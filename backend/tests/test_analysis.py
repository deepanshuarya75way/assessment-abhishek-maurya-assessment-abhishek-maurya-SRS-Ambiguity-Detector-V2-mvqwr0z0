"""Analysis API E2E: POST /api/v1/analysis (TEXT + deterministic engine).

HTTP-level contract tests (API_CONTRACT §4.3, Stage 07 amendment): 201 shape
(status `analyzed`, scored requirements with nested issues, breakdown, health),
validation branches, verified-user gating, CSRF, ownership by construction,
transactional rollback, requirements-cap refusal, and the per-user rate-limit
budget. No emails flow in this suite — verification is flipped directly in the
DB (mirrors test_auth's direct-write pattern).
"""

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.database import normalize_url
from app.core.rate_limit import reset_rate_limiter
from app.main import create_app
from app.models import Analysis, Requirement, User
from app.repositories.analysis import RequirementRepository
from app.services.segmentation import MAX_REQUIREMENTS, segment_requirements
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
def analysis_app(migrated_db: str) -> FastAPI:
    _ = migrated_db
    os.environ["JWT_SECRET"] = "stage06-test-jwt-secret-32-bytes-minimum"  # noqa: S105
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def analysis_client(analysis_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(analysis_app) as client:
        yield client


def _email(tag: str) -> str:
    return f"stage06-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _pw(tag: str = "staple") -> str:
    return f"correct-horse-{tag}-battery-99"


def _register(client: TestClient, email: str) -> Response:
    return client.post(
        "/api/v1/auth/register",
        json={"name": "Stage Six", "email": email, "password": _pw()},
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


async def _db_snapshot() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Plain-data snapshot of analyses + requirements (read inside the session;
    ORM objects would detach on close)."""
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            analyses = (await session.execute(select(Analysis))).scalars().all()
            a_rows = [
                {
                    "id": a.id,
                    "owner_id": a.owner_id,
                    "title": a.title,
                    "status": a.status,
                    "source_text": a.source_text,
                    "source_excerpt": a.source_excerpt,
                    "score": a.score,
                    "band": a.band,
                    "requirements_count": a.requirements_count,
                    "issues_count": a.issues_count,
                }
                for a in analyses
            ]
            reqs = (
                (await session.execute(select(Requirement).order_by(Requirement.position)))
                .scalars()
                .all()
            )
            r_rows = [
                {
                    "owner_id": r.owner_id,
                    "analysis_id": r.analysis_id,
                    "position": r.position,
                    "identifier": r.identifier,
                    "section": r.section,
                    "text": r.text,
                    "score": r.score,
                    "segmentation": dict(r.segmentation or {}),
                }
                for r in reqs
            ]
            return a_rows, r_rows
    finally:
        await engine.dispose()


def _login_verified(client: TestClient, tag: str) -> str:
    """Register → verify (direct DB flip) → login; session cookies land in the
    client's jar. Returns the account email."""
    email = _email(tag)
    assert _register(client, email).status_code == 201
    run(_verify_user(email))
    assert _login(client, email).status_code == 200
    return email


def _analyze(client: TestClient, payload: dict[str, object], **kw: object) -> Response:
    return client.post("/api/v1/analysis", json=payload, **kw)  # type: ignore[arg-type]


SAMPLE_SRS = (
    "# Functional Requirements\n\n"
    "FR-001: The system shall allow login with email.\n\n"
    "1. The admin must approve new accounts.\n"
    "- The audit log shall record every login attempt.\n\n"
    "The dashboard should load in under two seconds.\n"
)


# --- 201 shape ----------------------------------------------------------------


def test_create_analysis_returns_analyzed_detail(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "shape")
    resp = _analyze(analysis_client, {"title": "Login SRS", "text": SAMPLE_SRS})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Login SRS"
    assert body["status"] == "analyzed"
    assert body["source_type"] == "text"
    assert body["score"] == 96  # mean(100, 100, 90, 95), half-up
    assert body["band"] == "low"
    assert body["score_breakdown"]["base"] == 100
    assert body["score_breakdown"]["counts"] == {
        "low": 1,
        "medium": 1,
        "high": 0,
        "critical": 0,
    }
    assert body["health"] == {
        "measurability": 100,
        "specificity": 90,  # `every` −10
        "clarity": 95,  # `should` −5
        "completeness": 100,
    }
    assert body["ai_status"] == "skipped"
    assert body["ai_overview"] is None
    assert body["issues_count"] == 2
    assert body["requirements_count"] == 4
    # Contract-exact shape: no top-level `issues` (nested-only), no `source_excerpt`
    # (summary-only) in the detail response.
    assert "issues" not in body
    assert "source_excerpt" not in body
    assert body["created_at"] and body["updated_at"]
    uuid.UUID(body["id"])  # parses as UUID

    first, *rest = body["requirements"]
    assert first["position"] == 0
    assert first["identifier"] == "FR-001"
    assert first["section"] == "Functional Requirements"
    assert first["text"] == "The system shall allow login with email."
    assert first["score"] == 100  # clean: no findings
    assert first["severity"] is None
    assert first["issues_count"] == 0
    assert first["issues"] == []
    meta = first["segmentation"]
    assert meta["strategy"] == "requirement_id"
    assert meta["confidence"] == 0.95
    assert meta["start_offset"] >= 0 and meta["end_offset"] > meta["start_offset"]
    assert meta["line_start"] >= 1 and meta["line_end"] >= meta["line_start"]
    assert [r["position"] for r in body["requirements"]] == [0, 1, 2, 3]
    assert [r["identifier"] for r in rest] == ["1", None, None]
    assert [r["score"] for r in body["requirements"]] == [100, 100, 90, 95]
    assert [r["severity"] for r in body["requirements"]] == [None, None, "medium", "low"]

    every, should = body["requirements"][2]["issues"], body["requirements"][3]["issues"]
    assert [(i["detector_id"], i["severity"], i["phrase"]) for i in every] == [
        ("absolute-language", "medium", "every")
    ]
    assert [(i["detector_id"], i["severity"], i["phrase"]) for i in should] == [
        ("optional-language", "low", "should")
    ]
    flagged = every[0]
    assert flagged["category"] == "Absolute language"
    assert flagged["reason"] and flagged["recommendation"]  # explainability present
    assert flagged["ai_explanation"] is None
    assert "requirement_id" not in flagged  # nesting owns the parent link
    # Breakdown deductions reference the exact nested issue ids.
    nested_ids = {i["id"] for r in body["requirements"] for i in r["issues"]}
    assert {d["issue_id"] for d in body["score_breakdown"]["deductions"]} == nested_ids
    assert sorted(d["points"] for d in body["score_breakdown"]["deductions"]) == [5, 10]


def test_title_falls_back_when_missing_or_blank(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "title")
    no_title = _analyze(analysis_client, {"text": SAMPLE_SRS})
    assert no_title.json()["title"] == "Untitled SRS Analysis"
    blank_title = _analyze(analysis_client, {"title": "   ", "text": SAMPLE_SRS})
    assert blank_title.json()["title"] == "Untitled SRS Analysis"
    padded = _analyze(analysis_client, {"title": "  Padded  ", "text": SAMPLE_SRS})
    assert padded.json()["title"] == "Padded"


def test_explicit_null_document_id_and_ai_enhance_accepted(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "opts")
    resp = _analyze(
        analysis_client,
        {"text": SAMPLE_SRS, "document_id": None, "options": {"ai_enhance": True}},
    )
    assert resp.status_code == 201  # ai_enhance live since Stage 14 (no key → unconfigured)
    body = resp.json()
    assert body["ai_status"] == "unconfigured"
    assert body["ai_overview"] is None and body["ai_error"] is None
    assert body["status"] == "analyzed" and body["score"] is not None  # deterministic intact


def test_repeated_submits_create_distinct_analyses(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "twice")
    first = _analyze(analysis_client, {"text": SAMPLE_SRS})
    second = _analyze(analysis_client, {"text": SAMPLE_SRS})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]  # no dedup: honest 1:1 rows


# --- validation branches ------------------------------------------------------


def test_missing_or_empty_text_is_validation_error(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "missing")
    assert _analyze(analysis_client, {}).status_code == 400
    assert _analyze(analysis_client, {}).json()["error"]["code"] == "validation_error"
    empty = _analyze(analysis_client, {"text": ""})
    assert empty.json()["error"]["code"] == "validation_error"


def test_oversized_text_is_validation_error(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "big")
    resp = _analyze(analysis_client, {"text": "x" * 200_001})
    assert resp.status_code == 400
    body = resp.json()["error"]
    assert body["code"] == "validation_error"
    assert any("text" in detail.get("loc", []) for detail in body["details"])


def test_oversized_title_is_validation_error(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "longtitle")
    resp = _analyze(analysis_client, {"title": "t" * 201, "text": SAMPLE_SRS})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_blank_text_is_field_validation_error(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "blank")
    resp = _analyze(analysis_client, {"text": "   \n  "})
    assert resp.status_code == 400
    body = resp.json()["error"]
    assert body["code"] == "validation_error"
    assert any("text" in detail.get("loc", []) for detail in body["details"])
    analyses, requirements = run(_db_snapshot())
    assert analyses == [] and requirements == []  # refusal persists nothing


def test_signal_less_prose_detects_no_requirements(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "prose")
    resp = _analyze(
        analysis_client, {"text": "Just some prose without any requirement verbs here."}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_requirements_detected"
    analyses, requirements = run(_db_snapshot())
    assert analyses == [] and requirements == []  # refusal persists nothing


def test_document_id_rejected_before_stage_09(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "doc")
    resp = _analyze(analysis_client, {"text": SAMPLE_SRS, "document_id": str(uuid.uuid4())})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "document_analysis_unavailable"


def test_requirements_cap_refuses_with_counts(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "cap")
    lines = [f"{n}. The system shall satisfy requirement number {n}." for n in range(1, 2002)]
    resp = _analyze(analysis_client, {"text": "\n".join(lines)})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "text_too_large"
    assert error["details"] == {
        "requirements_found": MAX_REQUIREMENTS + 1,
        "max_requirements": MAX_REQUIREMENTS,
    }
    analyses, requirements = run(_db_snapshot())
    assert analyses == [] and requirements == []  # never truncate: refuse instead


# --- auth / CSRF / ownership --------------------------------------------------


def test_unauthenticated_rejected(analysis_client: TestClient) -> None:
    resp = _analyze(analysis_client, {"text": SAMPLE_SRS})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_forged_token_rejected(analysis_client: TestClient) -> None:
    resp = _analyze(
        analysis_client, {"text": SAMPLE_SRS}, headers={"Cookie": "access_token=forged"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_unverified_user_rejected(analysis_client: TestClient) -> None:
    email = _email("unverified")
    assert _register(analysis_client, email).status_code == 201
    assert _login(analysis_client, email).status_code == 200  # login works unverified
    resp = _analyze(analysis_client, {"text": SAMPLE_SRS})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "email_unverified"


def test_foreign_origin_rejected_allowlisted_origin_ok(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "csrf")
    evil = _analyze(analysis_client, {"text": SAMPLE_SRS}, headers={"Origin": "https://evil.test"})
    assert evil.status_code == 403
    assert evil.json()["error"]["code"] == "forbidden"
    ok_origin = _analyze(
        analysis_client, {"text": SAMPLE_SRS}, headers={"Origin": "http://localhost:3000"}
    )
    assert ok_origin.status_code == 201


def test_ownership_comes_from_session_spoofed_ids_ignored(
    analysis_client: TestClient,
) -> None:
    email = _login_verified(analysis_client, "owner")
    resp = _analyze(
        analysis_client,
        {"text": SAMPLE_SRS, "owner_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 201
    analyses, requirements = run(_db_snapshot())
    assert len(analyses) == 1 and len(requirements) == 4
    engine = create_async_engine(normalize_url(TEST_DATABASE_URL))

    async def _owner_id() -> uuid.UUID:
        try:
            async with AsyncSession(engine) as session:
                user = (await session.execute(select(User).where(User.email == email))).scalar_one()
                return user.id
        finally:
            await engine.dispose()

    owner_id = run(_owner_id())
    assert analyses[0]["owner_id"] == owner_id
    assert {r["owner_id"] for r in requirements} == {owner_id}
    assert {r["analysis_id"] for r in requirements} == {analyses[0]["id"]}


# --- persistence / transactions -----------------------------------------------


def test_persists_normalized_source_and_segment_rows(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "persist")
    windows_text = "FR-1: The system shall boot.\r\n\r\n- It must halt.   \r\n"
    resp = _analyze(analysis_client, {"text": windows_text})
    assert resp.status_code == 201
    analyses, requirements = run(_db_snapshot())
    assert len(analyses) == 1
    stored = analyses[0]
    assert stored["status"] == "analyzed"
    assert stored["score"] == 100 and stored["band"] == "low"  # both reqs clean
    assert stored["requirements_count"] == 2 and stored["issues_count"] == 0
    assert "\r" not in str(stored["source_text"])  # normalized form persisted
    assert str(stored["source_excerpt"]) == str(stored["source_text"])[:500]
    assert [r["position"] for r in requirements] == [0, 1]
    assert [r["text"] for r in requirements] == [
        "The system shall boot.",
        "It must halt.",
    ]
    assert requirements[0]["segmentation"]["strategy"] == "requirement_id"


def test_stored_source_resegments_identically(analysis_client: TestClient) -> None:
    _login_verified(analysis_client, "reseg")
    assert _analyze(analysis_client, {"text": SAMPLE_SRS}).status_code == 201
    analyses, requirements = run(_db_snapshot())
    source_text = str(analyses[0]["source_text"])
    resegmented = segment_requirements(source_text)
    assert [s.text for s in resegmented] == [r["text"] for r in requirements]
    assert [s.identifier for s in resegmented] == [r["identifier"] for r in requirements]


def test_mid_persist_failure_rolls_back_everything(
    analysis_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Non-raising client (test_errors precedent): the 500 envelope is the
    # assertion target, not the server-side exception.
    with TestClient(analysis_app, raise_server_exceptions=False) as quiet_client:
        _login_verified(quiet_client, "rollback")

        async def _boom(self: RequirementRepository, **kwargs: object) -> list[object]:
            raise RuntimeError("boom")

        monkeypatch.setattr(RequirementRepository, "create_many", _boom)
        resp = _analyze(quiet_client, {"text": SAMPLE_SRS})
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "internal_error"
    analyses, requirements = run(_db_snapshot())
    assert analyses == [] and requirements == []  # no partial analysis survives


# --- rate limiting --------------------------------------------------------------


def test_analysis_rate_limit_returns_429_with_retry_after(
    analysis_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_verified(analysis_client, "rl")
    monkeypatch.setenv("RATE_LIMIT_ANALYSIS_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        assert _analyze(analysis_client, {"text": SAMPLE_SRS}).status_code == 201
        assert _analyze(analysis_client, {"text": SAMPLE_SRS}).status_code == 201
        limited = _analyze(analysis_client, {"text": SAMPLE_SRS})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1
    finally:
        get_settings.cache_clear()
