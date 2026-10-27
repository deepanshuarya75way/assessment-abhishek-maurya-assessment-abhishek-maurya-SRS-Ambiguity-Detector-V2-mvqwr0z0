"""Storage port: binaries live here, metadata in Postgres (DATABASE_SCHEMA §3.5).

Keys are server-generated opaque paths (`documents/{user_id}/{document_id}/source`)
— never user input, never exposed to clients. Stage 08 shipped store (upload) +
delete (cleanup/cascade); Stage 19 adds the bounded read for signed-URL
downloads (objects are ≤10 MiB by the upload invariant, so a full read is safe).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageBackend(Protocol):
    """Object-store port. Implementations MUST confine every key under their
    root (defense in depth — keys are server-built, but a confused caller
    must never escape the bucket)."""

    def store_file(self, key: str, src: Path) -> None:
        """Persist `src` under `key` (implementations SHOULD move, not copy —
        the staged temp file becomes the stored object)."""
        ...

    def delete(self, key: str) -> None:
        """Remove `key`; a missing key is a no-op (idempotent cleanup)."""
        ...

    def read_bytes(self, key: str) -> bytes:
        """Return the full object at `key` (Stage 19: signed downloads).

        Raises `FileNotFoundError` when the object is missing (the service
        maps that to an honest 500 — a live row without bytes is OUR
        inconsistency, never the user's 404).
        """
        ...
