"""Declarative base + shared column mixins.

Conventions (the project contract): TIMESTAMPTZ everywhere, Python-generated
UUID PKs (no extension dependency), client AND server defaults kept in agreement.
"""

import datetime as dt

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Model registry root. Constraint/index names are explicit per table."""


class CreatedMixin:
    """`created_at` for every table (server clock, never client time)."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UpdatedMixin:
    """`updated_at` for mutable tables (analyses, users, credentials)."""

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
