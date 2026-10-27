"""Auth/crypto primitives: email normalization, argon2id passwords, 256-bit tokens
(sha256 at rest, constant-time compare), HS256 access JWTs.

No I/O, no framework imports. Secret-bearing values pass through here — this
module NEVER logs. CPU-bound hashing runs in a thread (never blocks the loop).
"""

import asyncio
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

from app.core.config import get_settings
from app.exceptions import InvalidTokenError

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 — JWT type label, not a credential
DOCUMENT_DOWNLOAD_TOKEN_TYPE = "document_download"  # noqa: S105 — ditto (Stage 19)
PRIVACY_EXPORT_TOKEN_TYPE = "privacy_export"  # noqa: S105 — ditto (Stage 23)
_JWT_ALGORITHM = "HS256"
_TOKEN_BYTES = 32  # 256-bit raw tokens (urlsafe ~43 chars)
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256

# Starter denylist (lowercase-compared). Length (≥12) is the real policy; this only
# rejects the most guessable choices. A breach-corpus check arrives when available.
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "password1234",
        "123456",
        "123456789",
        "123456789012",
        "qwerty",
        "qwerty123456",
        "abc123",
        "letmein",
        "letmein12345",
        "welcome",
        "welcome12345",
        "monkey",
        "dragon",
        "master",
        "sunshine",
        "princess",
        "football",
        "admin12345678",
        "user12345678",
        "changeme12345",
        "default12345",
        "test12345678",
        "srs123456789",
    }
)


def utcnow() -> datetime:
    """Timezone-aware UTC now (single clock for auth expiry math)."""
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    """Canonical email form: trimmed + lowercased (schema stores this)."""
    return email.strip().lower()


def _password_hasher() -> PasswordHasher:
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_COST,
        parallelism=settings.ARGON2_PARALLELISM,
    )


async def hash_password(password: str) -> str:
    """argon2id hash (PHC string). Runs off-loop; ~200–500 ms at prod params."""
    hasher = _password_hasher()
    return await asyncio.to_thread(hasher.hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verify. Unknown/corrupt hashes fail closed (False)."""
    hasher = _password_hasher()
    try:
        return await asyncio.to_thread(hasher.verify, hashed, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def is_common_password(password: str) -> bool:
    """Starter denylist check (case-insensitive)."""
    return password.lower() in COMMON_PASSWORDS


def generate_token() -> str:
    """256-bit cryptographically random token (urlsafe, for links/cookies)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """sha256 hex of a raw token — the ONLY form ever persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token_hash(candidate: str, stored_hex: str) -> bool:
    """Constant-time raw-token → stored-hash comparison."""
    return hmac.compare_digest(hash_token(candidate), stored_hex)


def hash_ip(ip: str) -> str:
    """One-way IP fingerprint for session-context rows (PII minimization)."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _jwt_secret() -> str:
    secret = get_settings().JWT_SECRET
    if not secret:
        raise RuntimeError(
            "JWT_SECRET is not configured (see backend/.env.example). "
            "Refusing to sign sessions without a secret."
        )
    return secret


def create_access_token(user_id: uuid.UUID, expires_minutes: int | None = None) -> str:
    """Short-lived HS256 access JWT (`sub` = user id, `type` = access)."""
    if expires_minutes is None:
        expires_minutes = get_settings().ACCESS_TOKEN_MINUTES
    now = utcnow()
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": ACCESS_TOKEN_TYPE,
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
        },
        _jwt_secret(),
        algorithm=_JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> uuid.UUID:
    """Validate an access JWT → owner id. Expired/forged/wrong-type → 401."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Your session has expired. Please log in again.") from None
    except jwt.InvalidTokenError:
        raise InvalidTokenError("Invalid session. Please log in again.") from None
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("Invalid session. Please log in again.")
    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str):
        raise InvalidTokenError("Invalid session. Please log in again.")
    try:
        return uuid.UUID(raw_sub)
    except ValueError:
        raise InvalidTokenError("Invalid session. Please log in again.") from None


def create_document_download_token(
    owner_id: uuid.UUID, document_id: uuid.UUID, expires_minutes: int
) -> str:
    """Short-lived HS256 download bearer (`sub` = owner, `doc` = document).

    Single purpose (the `type` separates it from session JWTs in BOTH
    directions), single document, short expiry (SECURITY_SPEC §5 caps
    signed-URL life at 15 min). The token travels in a query string — that
    is inherent to signed URLs (S3/Supabase presigned shape) and safe here
    ONLY because of the tight scope + expiry; it must never be logged.
    """
    now = utcnow()
    return jwt.encode(
        {
            "sub": str(owner_id),
            "type": DOCUMENT_DOWNLOAD_TOKEN_TYPE,
            "doc": str(document_id),
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
        },
        _jwt_secret(),
        algorithm=_JWT_ALGORITHM,
    )


def decode_document_download_token(token: str, document_id: uuid.UUID) -> uuid.UUID:
    """Validate a download bearer → owner id. Expired/forged/wrong-type /
    wrong-document ALL fail as 400 `invalid_token` (same envelope as email
    links — 256-bit HMAC is not enumerable, so honesty leaks no oracle).

    `document_id` is the path id: the token MUST name the document being
    fetched (a bearer for doc A never opens doc B).
    """
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("This download link has expired.") from None
    except jwt.InvalidTokenError:
        raise InvalidTokenError("This download link is invalid.") from None
    if payload.get("type") != DOCUMENT_DOWNLOAD_TOKEN_TYPE:
        # A session JWT (or any other token) is NOT a download bearer.
        raise InvalidTokenError("This download link is invalid.")
    if payload.get("doc") != str(document_id):
        raise InvalidTokenError("This download link is invalid.")
    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str):
        raise InvalidTokenError("This download link is invalid.")
    try:
        return uuid.UUID(raw_sub)
    except ValueError:
        raise InvalidTokenError("This download link is invalid.") from None


def create_privacy_export_token(owner_id: uuid.UUID, expires_minutes: int = 15) -> str:
    """Short-lived HS256 privacy-export ticket (`sub` = owner).

    The token is not sufficient by itself: export download also requires the
    caller's authenticated session to match `sub`.
    """
    now = utcnow()
    return jwt.encode(
        {
            "sub": str(owner_id),
            "type": PRIVACY_EXPORT_TOKEN_TYPE,
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
        },
        _jwt_secret(),
        algorithm=_JWT_ALGORITHM,
    )


def decode_privacy_export_token(token: str) -> uuid.UUID:
    """Validate a privacy-export ticket → owner id (400 `invalid_token`)."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("This export link has expired.") from None
    except jwt.InvalidTokenError:
        raise InvalidTokenError("This export link is invalid.") from None
    if payload.get("type") != PRIVACY_EXPORT_TOKEN_TYPE:
        raise InvalidTokenError("This export link is invalid.")
    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str):
        raise InvalidTokenError("This export link is invalid.")
    try:
        return uuid.UUID(raw_sub)
    except ValueError:
        raise InvalidTokenError("This export link is invalid.") from None
