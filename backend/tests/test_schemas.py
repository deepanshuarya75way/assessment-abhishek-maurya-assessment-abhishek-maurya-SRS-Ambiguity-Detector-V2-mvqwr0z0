"""Shared Pydantic models: pagination params + page envelope (no DB)."""

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.common import Page, PaginationParams


class _Item(BaseModel):
    id: int
    name: str


def test_pagination_defaults_and_offset() -> None:
    params = PaginationParams()
    assert (params.page, params.page_size, params.offset) == (1, 20, 0)
    assert PaginationParams(page=3, page_size=10).offset == 20


def test_pagination_rejects_out_of_range() -> None:
    for kwargs in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        with pytest.raises(ValidationError):
            PaginationParams(**kwargs)


def test_page_envelope_serializes() -> None:
    page = Page(items=[_Item(id=1, name="a")], page=1, page_size=20, total=1)
    assert page.model_dump() == {
        "items": [{"id": 1, "name": "a"}],
        "page": 1,
        "page_size": 20,
        "total": 1,
    }
