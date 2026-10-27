"""Shared API models: pagination (the project contract).

First consumers are the Stage 07+ list endpoints; services receive validated
PaginationParams, never raw ints. Sort vocabularies stay per-resource.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Validated `?page=&page_size=` query pair (usable as a FastAPI dependency)."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    """Uniform collection envelope: `{items, page, page_size, total}`."""

    items: list[T]
    page: int
    page_size: int
    total: int
