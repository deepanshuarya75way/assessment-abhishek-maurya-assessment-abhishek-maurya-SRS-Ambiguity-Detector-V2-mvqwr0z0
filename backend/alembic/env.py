"""Alembic environment: async engine from app config.

DSN resolution mirrors the app (DIRECT_DATABASE_URL preferred, DATABASE_URL fallback)
via :mod:`app.core.config` — migrations always target the same database the app uses.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401 — registers every table on Base.metadata
from alembic import context
from app.core.config import get_settings
from app.core.database import normalize_url
from app.models.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _db_url() -> str:
    settings = get_settings()
    url = settings.DIRECT_DATABASE_URL or settings.DATABASE_URL
    if not url:
        raise RuntimeError(
            "Set DATABASE_URL (or DIRECT_DATABASE_URL) to run migrations. "
            "See backend/.env.example."
        )
    return normalize_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _db_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
