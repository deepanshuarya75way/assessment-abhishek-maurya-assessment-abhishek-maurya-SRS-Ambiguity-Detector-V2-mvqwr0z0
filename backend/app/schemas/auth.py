"""Auth API boundary models (API_CONTRACT §4.2). Length/policy enforcement split:
schemas own shape + length; the service owns denylist + normalization depth."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    normalize_email,
)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("name")
    @classmethod
    def _collapse_name(cls, value: str) -> str:
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError("Name must not be blank.")
        return collapsed

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    # Non-empty only — the hash decides (never leak policy on login).
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class DeleteAccountRequest(BaseModel):
    confirmation: Literal["DELETE"]


class AuthUserResponse(BaseModel):
    """register/login shape (API_CONTRACT §4.2 — sessions ride cookies)."""

    id: uuid.UUID
    email: str
    is_verified: bool


class MeResponse(BaseModel):
    """GET /auth/me — safe identity subset (never hashes/tokens/keys)."""

    id: uuid.UUID
    email: str
    display_name: str | None
    is_verified: bool
    is_active: bool
    created_at: datetime
