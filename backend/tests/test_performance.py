"""Stage 25 performance/resource regression tests.

These tests avoid wall-clock microbenchmarks. They assert structural guarantees:
large text columns are not selected for list/dashboard summaries, dashboard
improvement counting stays in SQL, and timed-out extraction work remains bounded.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.repositories.analysis import AnalysisRepository
from app.repositories.dashboard import DashboardRepository
from app.services import documents as document_service


class _CountResult:
    def scalar_one(self) -> int:
        return 0


class _RowsResult:
    def all(self) -> list[Any]:
        return []

    def one_or_none(self) -> None:
        return None


class _FakeSession:
    def __init__(self, *, first_result_is_count: bool = True) -> None:
        self.statements: list[Any] = []
        self._first_result_is_count = first_result_is_count

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        if self._first_result_is_count and len(self.statements) == 1:
            return _CountResult()
        return _RowsResult()


def _compiled_sql(statement: Any) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True})).lower()


def test_pool_and_extractor_settings_validate_bounds() -> None:
    settings = Settings(
        DATABASE_POOL_SIZE=3,
        DATABASE_MAX_OVERFLOW=4,
        DATABASE_POOL_TIMEOUT_SECONDS=5,
        DATABASE_POOL_RECYCLE_SECONDS=120,
        DOCUMENT_EXTRACTOR_WORKERS=2,
    )
    assert settings.DATABASE_POOL_SIZE == 3
    assert settings.DATABASE_MAX_OVERFLOW == 4
    assert settings.DOCUMENT_EXTRACTOR_WORKERS == 2

    with pytest.raises(ValueError, match="DATABASE_POOL_SIZE"):
        Settings(DATABASE_POOL_SIZE=0)
    with pytest.raises(ValueError, match="DOCUMENT_EXTRACTOR_WORKERS"):
        Settings(DOCUMENT_EXTRACTOR_WORKERS=0)


def test_analysis_history_projection_excludes_large_source_text() -> None:
    async def _run() -> list[str]:
        session = _FakeSession()
        await AnalysisRepository(session).list_owned(  # type: ignore[arg-type]
            owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            offset=0,
            limit=20,
            sort="-created_at",
            band=None,
            source_type=None,
            q=None,
        )
        return [_compiled_sql(statement) for statement in session.statements]

    count_sql, page_sql = asyncio.run(_run())
    assert "count" in count_sql
    assert "source_text" not in page_sql
    assert "ai_overview" not in page_sql
    assert "score_breakdown" not in page_sql
    assert "source_excerpt" in page_sql


def test_dashboard_latest_projection_excludes_large_source_text() -> None:
    async def _run() -> str:
        session = _FakeSession(first_result_is_count=False)
        await DashboardRepository(session).latest(  # type: ignore[arg-type]
            owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001")
        )
        return _compiled_sql(session.statements[0])

    sql = asyncio.run(_run())
    assert "source_text" not in sql
    assert "ai_overview" not in sql
    assert "score_breakdown" not in sql
    assert "analyses.title" in sql


def test_dashboard_improved_count_uses_sql_window() -> None:
    async def _run() -> str:
        session = _FakeSession()
        await DashboardRepository(session).improved_count(  # type: ignore[arg-type]
            owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001")
        )
        return _compiled_sql(session.statements[0])

    sql = asyncio.run(_run())
    assert "lag(" in sql
    assert "previous_score" in sql
    assert "source_text" not in sql


def test_timed_out_extraction_holds_permit_until_worker_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    release_first = threading.Event()

    def _slow_extract(*_args: Any, **_kwargs: Any) -> tuple[str, str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            release_first.wait(timeout=1)
        return "validated", "extracted"

    monkeypatch.setattr(document_service, "_validate_and_extract", _slow_extract)
    document_service.shutdown_document_processing_executor()

    async def _run() -> None:
        kwargs = {
            "filename": "srs.txt",
            "content_type": "text/plain",
            "byte_size": 10,
            "sha256_hex": "0" * 64,
            "max_chars": 200_000,
            "max_workers": 1,
        }
        with pytest.raises(document_service.DocumentProcessingTimeoutError):
            await document_service._bounded_validate_and_extract(  # noqa: SLF001
                Path("unused"), timeout_seconds=0.02, **kwargs
            )
        assert calls == 1

        # The first timed-out parser is still running and still owns the sole
        # permit, so this call times out while waiting and does not enqueue a
        # second parser task.
        with pytest.raises(document_service.DocumentProcessingTimeoutError):
            await document_service._bounded_validate_and_extract(  # noqa: SLF001
                Path("unused"), timeout_seconds=0.02, **kwargs
            )
        assert calls == 1

        release_first.set()
        await asyncio.sleep(0.05)
        assert await document_service._bounded_validate_and_extract(  # noqa: SLF001
            Path("unused"), timeout_seconds=1, **kwargs
        ) == ("validated", "extracted")
        assert calls == 2

    try:
        asyncio.run(_run())
    finally:
        document_service.shutdown_document_processing_executor()
