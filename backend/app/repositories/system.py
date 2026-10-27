"""Infrastructure queries. Canonical minimal repository — business repositories
(Stage 04+) copy this shape: constructor takes the session, methods take intent."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SystemRepository:
    """Connectivity probes (no domain logic)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> None:
        """Prove the session reaches PostgreSQL (raises on failure)."""
        await self._session.execute(text("SELECT 1"))
