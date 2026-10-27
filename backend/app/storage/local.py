"""Local-filesystem storage backend (dev + single-node deploys).

Layout: `{STORAGE_LOCAL_DIR}/documents/{user_id}/{document_id}/source`.
Uploads stream to 0600 system-temp files (`mkstemp`) and are moved here on
success — atomic `os.replace` on the same filesystem, copy+unlink fallback
otherwise (either way the staged bytes become the object exactly once). Temp
files stay 0600 through the move. Nothing here is ever served over HTTP
directly — Stage 19 downloads go through the signed-URL handler (token +
owner checks, `Content-Disposition: attachment`), never static mounts.
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path


class LocalStorageBackend:
    """Filesystem-backed `StorageBackend` rooted at `root_dir`."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir).resolve()

    def _resolve(self, key: str) -> Path:
        """Map `key` to an absolute path, refusing anything that escapes root."""
        if not key or key.startswith("/") or "\\" in key or ".." in Path(key).parts:
            raise ValueError(f"refusing unsafe storage key: {key!r}")
        resolved = (self._root / key).resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError(f"storage key escapes root: {key!r}")
        return resolved

    def store_file(self, key: str, src: Path) -> None:
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Atomic same-filesystem move: the staged upload BECOMES the object.
            os.replace(src, dest)
        except OSError as exc:
            if exc.errno != errno.EXDEV:  # cross-device: copy, then remove source
                raise
            shutil.copy2(src, dest)
            src.unlink(missing_ok=True)

    def read_bytes(self, key: str) -> bytes:
        # `_resolve` confines under root first (a confused caller must never
        # read outside the bucket); a missing object raises FileNotFoundError.
        return self._resolve(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            dest = self._resolve(key)
        except ValueError:
            return  # caller bug, not data — nothing to remove
        dest.unlink(missing_ok=True)
        # Prune newly-empty user/document dirs (best-effort; never above root).
        parent = dest.parent
        while parent != self._root and self._root in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
