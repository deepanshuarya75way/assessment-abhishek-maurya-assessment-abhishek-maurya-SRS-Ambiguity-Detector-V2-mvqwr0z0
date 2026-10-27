"""Settings schemas (API_CONTRACT §4.7).

Stage 16 finalized profile fields; Stage 23 adds real privacy lifecycle settings.
"""

import datetime as dt

from pydantic import BaseModel, Field, field_validator


class ProfileResponse(BaseModel):
    """GET /settings/profile — the caller's own profile (verified users only)."""

    email: str
    display_name: str | None
    is_verified: bool
    is_active: bool
    created_at: dt.datetime


class ProfileUpdateRequest(BaseModel):
    """PATCH /settings/profile — `display_name` is the ONLY settable field.

    Email change is NOT in v1 (the address is identity + recovery anchor).
    Explicit `null` (or blank) clears the display name back to unset.
    """

    display_name: str | None = Field(max_length=100)

    @field_validator("display_name")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
