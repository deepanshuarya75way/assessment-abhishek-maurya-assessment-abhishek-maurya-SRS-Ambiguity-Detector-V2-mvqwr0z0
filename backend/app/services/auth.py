"""Authentication business logic (API_CONTRACT §4.2, SECURITY_SPEC §3).

Pure of HTTP: takes sessions + plain values, returns plain results + outbound
EmailMessages. The ROUTER sets cookies and schedules email via BackgroundTasks.

Anti-enumeration posture (spec §3): email-input endpoints (register/forgot/
resend) never reveal account existence (synthetic-201 / always-202 + uniform
timing via dummy hashing); token endpoints (256-bit, unguessable) return
honest 400s. Logs carry user/token ids only — never emails, tokens, or hashes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    create_access_token,
    generate_token,
    hash_ip,
    hash_password,
    hash_token,
    is_common_password,
    normalize_email,
    utcnow,
    verify_password,
)
from app.email.base import (
    TEMPLATE_ACCOUNT_EXISTS,
    TEMPLATE_RESET_PASSWORD,
    TEMPLATE_SECURITY_NOTICE,
    EmailMessage,
)
from app.exceptions import (
    AccountDisabledError,
    CurrentPasswordError,
    InvalidCredentialsError,
    InvalidTokenError,
    UnauthorizedError,
    WeakPasswordError,
)
from app.models.user import User
from app.repositories.auth import (
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.services.privacy import delete_account_with_lifecycle
from app.services.transactions import transactional

logger = get_logger(__name__)


@dataclass(frozen=True)
class UserInfo:
    """Plain authenticated-identity snapshot (router maps it to responses)."""

    id: uuid.UUID
    email: str
    display_name: str | None
    is_verified: bool
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class SessionTokens:
    """Fresh session pair. Raw refresh goes to the cookie; its hash is stored."""

    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class AuthResult:
    """Session-issuing outcome: identity + optional tokens + outbound email."""

    user: UserInfo
    tokens: SessionTokens | None
    emails: tuple[EmailMessage, ...] = field(default_factory=tuple)


def _info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_verified=user.is_verified,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _check_password_policy(password: str, email: str) -> None:
    """Denylist + email-local-part rules (length is schema-enforced; re-checked
    here so service-level callers can't bypass it)."""
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise WeakPasswordError("Password must be between 12 and 256 characters.")
    if is_common_password(password):
        raise WeakPasswordError()
    local = email.split("@")[0]
    if len(local) >= 4 and local in password.lower():
        raise WeakPasswordError("Password must not contain your email address.")


async def _dummy_password_work() -> None:
    """Burn one hash cycle so unknown-email paths time like real ones."""
    await hash_password("dummy-uniform-timing-work")


async def _issue_session(
    repo: RefreshTokenRepository,
    user: User,
    *,
    user_agent: str | None,
    ip: str | None,
    family_id: uuid.UUID | None = None,
) -> SessionTokens:
    raw_refresh = generate_token()
    await repo.create(
        owner_id=user.id,
        token_hash=hash_token(raw_refresh),
        family_id=family_id or uuid.uuid4(),
        expires_at=utcnow() + timedelta(days=get_settings().REFRESH_TOKEN_DAYS),
        user_agent=user_agent[:255] if user_agent else None,
        ip_hash=hash_ip(ip) if ip else None,
    )
    return SessionTokens(access_token=create_access_token(user.id), refresh_token=raw_refresh)


async def _duplicate_registration(email: str, user: User) -> AuthResult:
    """Synthetic response for an existing email, preserving anti-enumeration."""
    await _dummy_password_work()  # match the hash cost of a real registration
    logger.info("duplicate registration attempt user_id=%s", user.id)
    synthetic = UserInfo(
        id=uuid.uuid4(),
        email=email,
        display_name=None,
        is_verified=True,
        is_active=True,
        created_at=utcnow(),
    )
    notice = EmailMessage(to=email, template=TEMPLATE_ACCOUNT_EXISTS, context={})
    return AuthResult(user=synthetic, tokens=None, emails=(notice,))


@transactional
async def register(session: AsyncSession, *, name: str, email: str, password: str) -> AuthResult:
    """Create an account and issue a session, preserving anti-enumeration."""
    email_n = normalize_email(email)
    _check_password_policy(password, email_n)
    users = UserRepository(session)
    existing = await users.get_by_email(email_n)
    if existing is not None:
        return await _duplicate_registration(email_n, existing)
    try:
        password_hash = await hash_password(password)
        user = await users.create(email=email_n, display_name=name, password_hash=password_hash)
        user.is_verified = True
    except IntegrityError:
        # Lost a concurrent-registration race: roll back (rollback expires ORM
        # state) and re-read fresh before taking the duplicate path.
        await session.rollback()
        raced = await users.get_by_email(email_n)
        if raced is None:  # pragma: no cover — defensive; impossible post-conflict
            raise
        return await _duplicate_registration(email_n, raced)
    tokens = await _issue_session(RefreshTokenRepository(session), user, user_agent=None, ip=None)
    logger.info("user registered user_id=%s", user.id)
    return AuthResult(user=_info(user), tokens=tokens, emails=())


@transactional
async def login(
    session: AsyncSession, *, email: str, password: str, user_agent: str | None, ip: str | None
) -> AuthResult:
    """Validate credentials → session pair. Unknown email, IdP account,
    and bad password are indistinguishable (401 + dummy work)."""
    email_n = normalize_email(email)
    users = UserRepository(session)
    user = await users.get_by_email(email_n)
    if user is None or user.identity_provider != "local" or not user.password_hash:
        await _dummy_password_work()
        raise InvalidCredentialsError()
    if not await verify_password(password, user.password_hash):
        logger.info("login failed (bad password) user_id=%s", user.id)
        raise InvalidCredentialsError()
    if not user.is_active:
        logger.info("login refused (disabled) user_id=%s", user.id)
        raise AccountDisabledError()
    await users.record_login(user, utcnow())
    tokens = await _issue_session(
        RefreshTokenRepository(session), user, user_agent=user_agent, ip=ip
    )
    logger.info("login ok user_id=%s", user.id)
    return AuthResult(user=_info(user), tokens=tokens, emails=())


@transactional
async def refresh(
    session: AsyncSession, *, refresh_token: str | None, user_agent: str | None, ip: str | None
) -> AuthResult:
    """Rotate a refresh token (atomic). Re-presenting a ROTATED token revokes its
    whole family (theft signal); logged-out/expired/unknown tokens are plain 401s."""
    if not refresh_token:
        raise InvalidTokenError("Invalid session. Please log in again.")
    repo = RefreshTokenRepository(session)
    row = await repo.get_by_hash(hash_token(refresh_token))
    now = utcnow()
    if row is None:
        raise InvalidTokenError("Invalid session. Please log in again.")
    if row.revoked_at is not None:
        if row.replaced_by_hash is not None:
            await repo.revoke_family(row.family_id, now=now)
            # Commit BEFORE raising: @transactional rolls back on error, which
            # would otherwise undo the theft response (see transactions.py).
            await session.commit()
            logger.warning("refresh reuse detected family_id=%s", row.family_id)
            raise InvalidTokenError("Session revoked. Please log in again.")
        raise InvalidTokenError("Invalid session. Please log in again.")
    if row.expires_at <= now:
        raise InvalidTokenError("Your session has expired. Please log in again.")
    user = await UserRepository(session).get_by_id(row.owner_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("Invalid session. Please log in again.")
    new_raw = generate_token()
    await repo.mark_rotated(row, new_hash=hash_token(new_raw), now=now)
    await repo.create(
        owner_id=user.id,
        token_hash=hash_token(new_raw),
        family_id=row.family_id,
        expires_at=now + timedelta(days=get_settings().REFRESH_TOKEN_DAYS),
        user_agent=user_agent[:255] if user_agent else None,
        ip_hash=hash_ip(ip) if ip else None,
    )
    logger.info("session refreshed user_id=%s", user.id)
    return AuthResult(
        user=_info(user),
        tokens=SessionTokens(access_token=create_access_token(user.id), refresh_token=new_raw),
        emails=(),
    )


@transactional
async def logout(session: AsyncSession, *, refresh_token: str | None) -> None:
    """Revoke the presented refresh token (idempotent; possession IS the credential,
    so logout works even with an expired access token)."""
    if not refresh_token:
        return
    repo = RefreshTokenRepository(session)
    row = await repo.get_by_hash(hash_token(refresh_token))
    if row is not None and row.revoked_at is None:
        await repo.revoke(row, now=utcnow())
        logger.info("logout ok owner_id=%s", row.owner_id)


@transactional
async def forgot_password(session: AsyncSession, *, email: str) -> tuple[EmailMessage, ...]:
    """Issue a reset token for active accounts (verified or not). Unknown /
    inactive addresses are silently accepted (always-202, no oracle)."""
    settings = get_settings()
    email_n = normalize_email(email)
    user = await UserRepository(session).get_by_email(email_n)
    if user is None or not user.is_active:
        return ()
    repo = PasswordResetTokenRepository(session)
    await repo.delete_pending_for_owner(user.id)
    raw_token = generate_token()
    await repo.create(
        owner_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=utcnow() + timedelta(minutes=settings.PASSWORD_RESET_MINUTES),
    )
    logger.info("password reset requested user_id=%s", user.id)
    return (
        EmailMessage(
            to=email_n,
            template=TEMPLATE_RESET_PASSWORD,
            context={
                "token": raw_token,
                "expiry_minutes": str(settings.PASSWORD_RESET_MINUTES),
            },
        ),
    )


@transactional
async def reset_password(
    session: AsyncSession, *, token: str, new_password: str
) -> tuple[EmailMessage, ...]:
    """Consume a reset token → new password + logout-everywhere + notice."""
    repo = PasswordResetTokenRepository(session)
    row = await repo.get_by_hash(hash_token(token))
    now = utcnow()
    if row is None or row.consumed_at is not None or row.expires_at <= now:
        raise InvalidTokenError()
    users = UserRepository(session)
    user = await users.get_by_id(row.owner_id)
    if user is None or not user.is_active:
        raise InvalidTokenError()
    _check_password_policy(new_password, user.email)
    await users.set_password_hash(user, await hash_password(new_password))
    await repo.mark_consumed(row, now=now)
    await repo.delete_pending_for_owner(user.id)
    await RefreshTokenRepository(session).revoke_all_for_owner(user.id, now=now)
    logger.info("password reset user_id=%s", user.id)
    return (
        EmailMessage(
            to=user.email,
            template=TEMPLATE_SECURITY_NOTICE,
            context={
                "title": "Password reset",
                "detail": (
                    "Your password was changed via a reset link. All other sessions "
                    "were signed out."
                ),
            },
        ),
    )


@transactional
async def change_password(
    session: AsyncSession, *, user_id: uuid.UUID, current_password: str, new_password: str
) -> tuple[EmailMessage, ...]:
    """Authenticated password change (current password required) + logout of all
    other sessions (the calling access token expires naturally within minutes)."""
    users = UserRepository(session)
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError()
    if (
        user.identity_provider != "local"
        or not user.password_hash
        or not await verify_password(current_password, user.password_hash)
    ):
        raise CurrentPasswordError()
    _check_password_policy(new_password, user.email)
    await users.set_password_hash(user, await hash_password(new_password))
    await PasswordResetTokenRepository(session).delete_pending_for_owner(user.id)
    await RefreshTokenRepository(session).revoke_all_for_owner(user.id, now=utcnow())
    logger.info("password changed user_id=%s", user.id)
    return (
        EmailMessage(
            to=user.email,
            template=TEMPLATE_SECURITY_NOTICE,
            context={
                "title": "Password changed",
                "detail": "Your password was changed. All other sessions were signed out.",
            },
        ),
    )


async def delete_account(session: AsyncSession, *, user_id: uuid.UUID) -> tuple[EmailMessage, ...]:
    """Hard-delete the account + storage objects + farewell notice.

    `delete_account_with_lifecycle` owns the transaction/storage ordering. The
    returned email is captured before the row is deleted.
    """
    email = await delete_account_with_lifecycle(session, user_id=user_id)
    return (
        EmailMessage(
            to=email,
            template=TEMPLATE_SECURITY_NOTICE,
            context={
                "title": "Account deleted",
                "detail": ("Your account and all associated data were permanently deleted."),
            },
        ),
    )


async def get_user_info(session: AsyncSession, user_id: uuid.UUID) -> UserInfo | None:
    """Read-only identity snapshot for /me (no transaction needed)."""
    user = await UserRepository(session).get_by_id(user_id)
    return _info(user) if user is not None else None
