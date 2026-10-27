"""Async PostgreSQL engine + session factory (SQLAlchemy 2.0 + asyncpg).

DSN handling rules (SECURITY_SPEC): the URL is accepted from `DATABASE_URL` only,
never logged, never returned, never echoed in errors — exception chains that could
carry it are deliberately suppressed (`from None`).

Lifecycle: process-wide lazy engine, disposed by the app lifespan on shutdown
(tests dispose per test). Requests get one session each via the `get_session`
FastAPI dependency; infrastructure probes (readiness) take a short-lived session
from `get_session_factory`.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def normalize_url(raw: str) -> str:
    """Coerce `postgresql://` / `postgres://` to the asyncpg driver URL.

    Raises RuntimeError (value withheld) for anything else — non-Postgres URLs are
    rejected loudly so nothing can silently run on the wrong engine.
    """
    if raw.startswith("postgresql+asyncpg://"):
        return raw
    for prefix in ("postgresql://", "postgres://"):
        if raw.startswith(prefix):
            return "postgresql+asyncpg://" + raw[len(prefix) :]
    raise RuntimeError(
        "DATABASE_URL must use the postgresql:// scheme (see backend/.env.example). "
        "Value withheld."
    )


def get_engine() -> AsyncEngine:
    """Process-wide lazy engine (pool_pre_ping: stale pooled conns are recycled)."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    settings = get_settings()
    raw_url = settings.DATABASE_URL
    if not raw_url:
        raise RuntimeError("DATABASE_URL is not configured (see backend/.env.example).")
    try:
        _engine = create_async_engine(
            normalize_url(raw_url),
            pool_pre_ping=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
            pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
        )
    except Exception:
        # from None: SQLAlchemy parse errors echo the URL — must not reach tracebacks.
        raise RuntimeError("Invalid DATABASE_URL (see backend/.env.example).") from None
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the process engine (expire_on_commit=False)."""
    get_engine()
    assert _session_factory is not None  # get_engine() always sets both together
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding one session per request (routes from Stage 04)."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose + forget the cached engine (lifespan shutdown; tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
