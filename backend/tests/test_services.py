"""Service layer: readiness aggregation + @transactional.

Readiness ok/transaction tests need PostgreSQL (migrated_db); the not_configured
and unreachable cases need none. All fixture identities are @example.com fakes.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import dispose_engine
from app.models import User
from app.services.readiness import get_readiness
from app.services.transactions import transactional
from tests.conftest import db_test_session, run


def test_readiness_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        report = run(get_readiness())
    finally:
        get_settings.cache_clear()
    assert report.status == "ready"
    assert report.checks == {"database": "not_configured"}


def test_readiness_ok(migrated_db: str) -> None:
    async def _probe() -> None:
        try:
            report = await get_readiness()
            assert report.status == "ready"
            assert report.checks == {"database": "ok"}
        finally:
            await dispose_engine()

    run(_probe())


def test_readiness_error_on_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/db")
    get_settings.cache_clear()

    async def _probe() -> None:
        try:
            report = await get_readiness()
            assert report.status == "degraded"  # truthful: never a false "ready"
            assert report.checks == {"database": "error"}
        finally:
            await dispose_engine()

    try:
        run(_probe())
    finally:
        get_settings.cache_clear()


@transactional
async def _create_user(session: AsyncSession, email: str) -> uuid.UUID:
    user = User(email=email, display_name="Tx Fixture")
    session.add(user)
    await session.flush()
    return user.id


@transactional
async def _create_then_boom(session: AsyncSession, email: str) -> None:
    session.add(User(email=email, display_name="Tx Fixture"))
    await session.flush()
    raise ValueError("boom")


def test_transactional_commits(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            uid = await _create_user(s, "tx-ok@example.com")
            assert isinstance(uid, uuid.UUID)
            assert await s.scalar(select(func.count()).select_from(User)) == 1

    run(_case())


def test_transactional_rolls_back(migrated_db: str) -> None:
    async def _case() -> None:
        async with db_test_session() as s:
            with pytest.raises(ValueError, match="boom"):
                await _create_then_boom(s, "tx-fail@example.com")
            assert await s.scalar(select(func.count()).select_from(User)) == 0

    run(_case())
