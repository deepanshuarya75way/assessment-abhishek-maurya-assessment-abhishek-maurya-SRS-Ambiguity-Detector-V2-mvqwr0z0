"""Shared pytest fixtures.

Database strategy: tests target a REAL PostgreSQL (never SQLite — dialect fidelity
is the point). The suite connects to TEST_DATABASE_URL (default: conventional local
test DB, overridable). If PostgreSQL is unreachable, DB tests SKIP with a clear
message instead of failing — CI/devs without local PG still get the non-DB suite.

Event-loop rule: asyncpg pools bind to their creating loop, so EVERY database test
does all of its work (session + statements + cleanup + engine dispose) inside ONE
`run()` call via the `db_test_session()` context manager. Never share an engine
across `run()` calls.
"""

import asyncio
import os
import re
from collections.abc import AsyncIterator, Coroutine, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/srs_test"
)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Drive one coroutine on a fresh event loop (no async test plugin needed)."""
    return asyncio.run(coro)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _maintenance_url(test_url: str) -> str:
    from app.core.database import normalize_url

    return str(make_url(normalize_url(test_url)).set(database="postgres"))


async def _ensure_test_database(test_url: str) -> None:
    """Create the scratch database if missing (connect role needs CREATEDB)."""
    from app.core.database import normalize_url

    probe = create_async_engine(normalize_url(test_url))
    try:
        async with probe.connect():
            return
    except Exception as exc:  # asyncpg connect errors arrive unwrapped (no SQLA facade)
        if "does not exist" not in str(exc):
            raise  # server down, auth failure, … — caller decides skip vs fail
    finally:
        await probe.dispose()
    dbname = make_url(normalize_url(test_url)).database
    if not dbname or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", dbname):
        raise RuntimeError(f"Refusing to CREATE DATABASE with unexpected name {dbname!r}.")
    maint = create_async_engine(_maintenance_url(test_url), isolation_level="AUTOCOMMIT")
    try:
        async with maint.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await maint.dispose()


@pytest.fixture(scope="session")
def migrated_db() -> Generator[str, None, None]:
    """Session DB: ensure database exists, `alembic upgrade head`, yield the URL."""
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings
    from app.core.database import dispose_engine

    try:
        run(_ensure_test_database(TEST_DATABASE_URL))
    except (OSError, OperationalError) as exc:
        pytest.skip(
            f"PostgreSQL test database unreachable ({type(exc).__name__}); "
            "set TEST_DATABASE_URL to run DB tests."
        )
    old_url, old_direct = os.environ.get("DATABASE_URL"), os.environ.get("DIRECT_DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ.pop("DIRECT_DATABASE_URL", None)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        command.upgrade(cfg, "head")
        yield TEST_DATABASE_URL
    finally:
        run(dispose_engine())  # no-op unless a test leaked an engine
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        if old_direct is not None:
            os.environ["DIRECT_DATABASE_URL"] = old_direct
        get_settings.cache_clear()


@asynccontextmanager
async def db_test_session() -> AsyncIterator[AsyncSession]:
    """One session + full cleanup + engine dispose, all inside the caller's loop."""
    from app.core.database import dispose_engine, get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        # Clear failed-transaction state first: bodies often end on an expected error.
        await session.rollback()
        for table in (
            "ai_provider_credentials",
            "issues",
            "requirements",
            "analyses",
            "documents",
            "refresh_tokens",
            "email_verification_tokens",
            "password_reset_tokens",
            "user_preferences",
            "users",
        ):
            # Static allowlist — no user input can reach this statement.
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.commit()
        await session.close()
        await dispose_engine()
