"""Data-access layer: SQLAlchemy lives here and ONLY here.

Repositories hold a session and expose one intention-revealing method per query.
No business rules, no HTTP, no commits (transactions belong to services).
"""

from app.repositories.system import SystemRepository

__all__ = ["SystemRepository"]
