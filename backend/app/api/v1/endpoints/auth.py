"""Auth endpoints (API_CONTRACT §4.2). Thin: guards → service → cookies/email.

Cookies (contract §1): `access_token` + `refresh_token`, HttpOnly, Secure in
prod, SameSite=Lax, Path=/. Email sends are post-commit BackgroundTasks
(uniform response timing + resend endpoints as the recovery path).
"""

from typing import Annotated, cast

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import auth_guard, auth_user_guard, get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.email.base import EmailMessage, EmailService
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services import auth as auth_service
from app.services.auth import AuthResult, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _email_service(request: Request) -> EmailService:
    """Adapter wired at startup (tests override `app.state.email_service`)."""
    service = getattr(request.app.state, "email_service", None)
    if service is None:  # pragma: no cover — create_app always wires it
        from app.email import get_email_service

        return get_email_service()
    return cast(EmailService, service)


async def _send_email(service: EmailService, message: EmailMessage) -> None:
    await service.send(message)  # adapters never raise (port contract)


def _schedule_email(
    tasks: BackgroundTasks, service: EmailService, messages: tuple[EmailMessage, ...]
) -> None:
    for message in messages:
        tasks.add_task(_send_email, service, message)


def _set_session_cookies(response: Response, result: AuthResult) -> None:
    if result.tokens is None:  # pragma: no cover — programmer error
        raise RuntimeError("Auth endpoint expected session tokens, got none.")
    settings = get_settings()
    secure = settings.is_production
    response.set_cookie(
        ACCESS_COOKIE,
        result.tokens.access_token,
        max_age=settings.ACCESS_TOKEN_MINUTES * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        result.tokens.refresh_token,
        max_age=settings.REFRESH_TOKEN_DAYS * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    # Attrs mirror _set_session_cookies (esp. path) so browsers drop them.
    secure = get_settings().is_production
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(REFRESH_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")


def _request_context(request: Request) -> tuple[str | None, str | None]:
    """User-agent + socket IP for session-context rows (never trust XFF here)."""
    ip = request.client.host if request.client else None
    return request.headers.get("user-agent"), ip


def _auth_user(result: AuthResult) -> AuthUserResponse:
    return AuthUserResponse(
        id=result.user.id, email=result.user.email, is_verified=result.user.is_verified
    )


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_guard("register"))],
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthUserResponse:
    result = await auth_service.register(
        session, name=body.name, email=str(body.email), password=body.password
    )
    if result.tokens is not None:
        _set_session_cookies(response, result)
    _schedule_email(tasks, _email_service(request), result.emails)
    return _auth_user(result)


@router.post(
    "/login",
    response_model=AuthUserResponse,
    dependencies=[Depends(auth_guard("login"))],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthUserResponse:
    user_agent, ip = _request_context(request)
    result = await auth_service.login(
        session, email=str(body.email), password=body.password, user_agent=user_agent, ip=ip
    )
    _set_session_cookies(response, result)
    return _auth_user(result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth_guard("logout"))],
)
async def logout(
    session: Annotated[AsyncSession, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    await auth_service.logout(session, refresh_token=refresh_token)
    # Cookies go on the RETURNED response: FastAPI drops the injected Response
    # when the endpoint returns a Response object.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookies(response)
    return response


@router.post(
    "/refresh",
    response_model=AuthUserResponse,
    dependencies=[Depends(auth_guard("refresh"))],
)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> AuthUserResponse:
    user_agent, ip = _request_context(request)
    result = await auth_service.refresh(
        session, refresh_token=refresh_token, user_agent=user_agent, ip=ip
    )
    _set_session_cookies(response, result)
    return _auth_user(result)


@router.get("/me", response_model=MeResponse)
async def me(user: Annotated[UserInfo, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_verified=user.is_verified,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth_guard("forgot"))],
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    emails = await auth_service.forgot_password(session, email=str(body.email))
    _schedule_email(tasks, _email_service(request), emails)
    return {}


@router.post(
    "/reset-password",
    dependencies=[Depends(auth_guard("reset"))],
)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    emails = await auth_service.reset_password(
        session, token=body.token, new_password=body.new_password
    )
    _schedule_email(tasks, _email_service(request), emails)
    return {}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserInfo, Depends(auth_user_guard("change"))],
) -> dict[str, object]:
    # user arrives via auth_user_guard (identity + CSRF + per-user rate limit).
    emails = await auth_service.change_password(
        session,
        user_id=user.id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    _schedule_email(tasks, _email_service(request), emails)
    return {}


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserInfo, Depends(auth_user_guard("delete"))],
) -> Response:
    emails = await auth_service.delete_account(session, user_id=user.id)
    _schedule_email(tasks, _email_service(request), emails)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookies(response)  # on the returned response (see logout)
    return response
