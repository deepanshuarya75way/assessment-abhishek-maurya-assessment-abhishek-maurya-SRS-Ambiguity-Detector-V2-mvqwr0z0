"""Run configured privacy retention once.

Usage:
    python -m app.cli.purge_retention

This is a Stage 23 maintenance seam, not a scheduler. Deployment can wire it to
cron/platform jobs later.
"""

from __future__ import annotations

import asyncio

from app.core.database import dispose_engine, get_session_factory
from app.services.privacy import enforce_configured_retention


async def _amain() -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await enforce_configured_retention(session)
    print(  # noqa: T201 - CLI command output, never includes user content/secrets.
        "retention purge complete: "
        f"users_scanned={result.users_scanned} "
        f"deleted_analyses={result.deleted_analyses} "
        f"deleted_documents={result.deleted_documents}"
    )
    await dispose_engine()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
