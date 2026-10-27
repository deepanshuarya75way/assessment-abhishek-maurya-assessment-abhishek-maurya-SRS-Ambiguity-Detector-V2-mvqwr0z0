from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.storage.supabase import SupabaseStorageBackend


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content


class _FakeClient:
    calls: list[dict[str, Any]] = []
    responses: list[_FakeResponse] = []

    def __init__(self, **_: Any) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    @classmethod
    def reset(cls, responses: list[_FakeResponse]) -> None:
        cls.calls = []
        cls.responses = responses

    @classmethod
    def _pop(cls) -> _FakeResponse:
        assert cls.responses, "test did not configure a fake Supabase response"
        return cls.responses.pop(0)

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        content = kwargs.get("content")
        if content is not None and hasattr(content, "read"):
            self.calls[-1]["uploaded"] = content.read()
        return self._pop()

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self._pop()

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._pop()


def _backend() -> SupabaseStorageBackend:
    return SupabaseStorageBackend(
        url="https://project.supabase.co",
        service_role_key="service-role-secret",
        bucket="srs-documents",
    )


def test_supabase_store_uploads_object_and_removes_staged_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("app.storage.supabase.httpx.Client", _FakeClient)
    _FakeClient.reset([_FakeResponse(200, b"{}")])
    staged = tmp_path / "upload.tmp"
    staged.write_bytes(b"FR-001: The system shall allow login.")

    _backend().store_file("documents/user-id/document-id/source", staged)

    assert not staged.exists()
    call = _FakeClient.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == (
        "https://project.supabase.co/storage/v1/object/"
        "srs-documents/documents/user-id/document-id/source"
    )
    assert call["uploaded"] == b"FR-001: The system shall allow login."
    assert call["headers"]["Authorization"] == "Bearer service-role-secret"
    assert call["headers"]["apikey"] == "service-role-secret"
    assert call["headers"]["x-upsert"] == "false"


def test_supabase_read_maps_404_to_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.storage.supabase.httpx.Client", _FakeClient)
    _FakeClient.reset([_FakeResponse(404)])

    with pytest.raises(FileNotFoundError):
        _backend().read_bytes("documents/user-id/document-id/source")


def test_supabase_read_returns_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.storage.supabase.httpx.Client", _FakeClient)
    _FakeClient.reset([_FakeResponse(200, b"stored")])

    assert _backend().read_bytes("documents/user-id/document-id/source") == b"stored"


def test_supabase_delete_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.storage.supabase.httpx.Client", _FakeClient)
    _FakeClient.reset([_FakeResponse(200)])

    _backend().delete("documents/user-id/document-id/source")

    call = _FakeClient.calls[0]
    assert call["method"] == "DELETE"
    assert call["json"] == {"prefixes": ["documents/user-id/document-id/source"]}


@pytest.mark.parametrize("key", ["", "/absolute", "documents/../escape", "a//b", r"a\\b"])
def test_supabase_refuses_unsafe_keys(key: str) -> None:
    with pytest.raises(ValueError):
        _backend().read_bytes(key)


def test_settings_require_supabase_storage_fields() -> None:
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        Settings(STORAGE_BACKEND="supabase")

    settings = Settings(
        STORAGE_BACKEND="supabase",
        SUPABASE_URL="https://project.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="service-role-secret",
        SUPABASE_STORAGE_BUCKET="srs-documents",
    )
    assert settings.STORAGE_BACKEND == "supabase"
