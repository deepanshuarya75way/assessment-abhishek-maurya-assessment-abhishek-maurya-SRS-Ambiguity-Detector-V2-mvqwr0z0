"""Shared v1 dependencies: session identity, CSRF origin check, auth rate limits.

Future resource routers (analysis, documents, …) reuse `get_current_user` /
`get_current_verified_user` — identity ALWAYS comes from the session, never
from client-supplied ids (IDOR rule, SECURITY_SPEC §2).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.rate_limit import check_rate_limit
from app.core.security import decode_access_token
from app.exceptions import (
    ForbiddenError,
    InvalidTokenError,
    UnauthorizedError,
)
from app.services.auth import UserInfo, get_user_info


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> UserInfo:
    """Session identity from the access cookie (401 on missing/invalid/expired
    token, deleted user, or deactivated account)."""
    if not access_token:
        raise UnauthorizedError()
    try:
        user_id = decode_access_token(access_token)
    except InvalidTokenError:
        raise UnauthorizedError() from None  # session context is always 401
    info = await get_user_info(session, user_id)
    if info is None or not info.is_active:
        raise UnauthorizedError()
    return info


async def get_current_verified_user(
    user: Annotated[UserInfo, Depends(get_current_user)],
) -> UserInfo:
    """Compatibility dependency: app access requires authentication, not email confirmation."""
    return user


async def verify_origin(request: Request) -> None:
    """CSRF guard for cookie-authed mutations: a present Origin (else Referer)
    must be allowlisted; absent headers = non-browser client (allowed — no
    ambient authority to forge)."""
    origins = {o.rstrip("/") for o in get_settings().BACKEND_CORS_ORIGINS}
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") not in origins:
            raise ForbiddenError("Cross-origin request refused.")
        return
    referer = request.headers.get("referer")
    if referer:
        try:
            parts = urlsplit(referer)
            ref_origin = f"{parts.scheme}://{parts.netloc}".rstrip("/")
        except ValueError:
            raise ForbiddenError("Cross-origin request refused.") from None
        if not parts.scheme or not parts.netloc or ref_origin not in origins:
            raise ForbiddenError("Cross-origin request refused.")


def auth_guard(endpoint: str) -> Callable[[Request], Awaitable[None]]:
    """Combined CSRF + per-IP rate-limit gate for anonymous auth mutations."""

    async def _guard(request: Request) -> None:
        await verify_origin(request)
        client_ip = request.client.host if request.client else "unknown"
        check_rate_limit(f"auth:{endpoint}:{client_ip}")

    return _guard


def auth_user_guard(endpoint: str) -> Callable[..., Awaitable[UserInfo]]:
    """Authenticated mutation gate: identity + CSRF + per-user rate limit."""

    async def _guard(
        request: Request, user: Annotated[UserInfo, Depends(get_current_user)]
    ) -> UserInfo:
        await verify_origin(request)
        check_rate_limit(f"auth:{endpoint}:user:{user.id}")
        return user

    return _guard


def verified_user_guard(
    bucket: str, *, limit: Callable[[], int] | None = None
) -> Callable[..., Awaitable[UserInfo]]:
    """Authenticated resource gate: identity + CSRF + per-user limit.

    `bucket` names the rate-limit bucket (`{bucket}:user:{id}`); `limit` is a
    zero-arg callable resolving the per-minute budget AT REQUEST TIME — the
    value must never be frozen at import (env retunes + tests would break).
    `None` keeps the auth default budget.
    """

    async def _guard(
        request: Request, user: Annotated[UserInfo, Depends(get_current_verified_user)]
    ) -> UserInfo:
        await verify_origin(request)
        check_rate_limit(f"{bucket}:user:{user.id}", limit=limit() if limit else None)
        return user

    return _guard
