"""File storage abstraction (local FS and Supabase Storage adapters).

Feature code resolves the backend through :func:`get_storage_backend` and
programs to the `StorageBackend` protocol — no provider imports outside this
package (SECURITY_SPEC §5: storage details never leak into the engine).
"""

from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.supabase import SupabaseStorageBackend

__all__ = [
    "LocalStorageBackend",
    "StorageBackend",
    "SupabaseStorageBackend",
    "get_storage_backend",
    "storage_key_for_document",
]


def storage_key_for_document(owner_id: uuid.UUID, document_id: uuid.UUID) -> str:
    """Server-generated opaque object key (UUIDs only — no user input can
    reach a storage path, ever). Single convention: upload + delete agree."""
    return f"documents/{owner_id}/{document_id}/source"


def get_storage_backend() -> StorageBackend:
    """Resolve the configured backend (fail closed on unknown values)."""
    settings = get_settings()
    if settings.STORAGE_BACKEND == "local":
        return LocalStorageBackend(settings.STORAGE_LOCAL_DIR)
    if settings.STORAGE_BACKEND == "supabase":
        assert settings.SUPABASE_URL is not None
        assert settings.SUPABASE_SERVICE_ROLE_KEY is not None
        assert settings.SUPABASE_STORAGE_BUCKET is not None
        return SupabaseStorageBackend(
            url=settings.SUPABASE_URL,
            service_role_key=settings.SUPABASE_SERVICE_ROLE_KEY,
            bucket=settings.SUPABASE_STORAGE_BUCKET,
        )
    raise RuntimeError(f"Unknown STORAGE_BACKEND: {settings.STORAGE_BACKEND!r}")
