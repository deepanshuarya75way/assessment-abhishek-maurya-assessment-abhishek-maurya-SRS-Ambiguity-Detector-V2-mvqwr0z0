"""User-owned provider credentials (AI_PROVIDER_SPEC §5, API_CONTRACT §4.6).

The vault boundary: plaintext keys enter through CREATE/ROTATE bodies, get
Fernet-encrypted immediately, and NEVER leave again — responses are
allowlist-serialized metadata (`masked_key` = 12 bullets + last4). Tests
decrypt server-side and hand plaintext to the adapter in-process.

Rules enforced here: one ENABLED credential per (owner, provider) (soft rows
may coexist for history), exactly one default per owner (partial unique
indexes + `IntegrityError → 409` on races), each key fingerprint unique per
(owner, provider), labels stripped with blank→None. `NotFoundError(
"ai_provider")` doubles as the IDOR guard (missing and foreign both read
404 — no oracle). Log vocabulary is ids + provider ids only — a breach of
this reads as plaintext keys in the log store.
"""

import uuid
from datetime import datetime
from time import perf_counter

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import ProviderError
from app.ai.registry import PROVIDER_ORDER, is_supported_provider, resolve_adapter
from app.core.logging import get_logger
from app.core.security import utcnow
from app.core.vault import (
    VAULT_VERSION,
    VaultError,
    decrypt_secret,
    encrypt_secret,
    fingerprint_secret,
)
from app.exceptions import ConflictError, InternalError, NotFoundError, ValidationError
from app.models.ai_credential import AICredential
from app.repositories.ai_providers import AICredentialRepository
from app.services.transactions import transactional

logger = get_logger(__name__)

_LABEL_MAX_LENGTH = 80
_FALLBACK_RANK_MAX = 32767
_API_KEY_MIN_LENGTH = 4
_API_KEY_MAX_LENGTH = 2000
_ERROR_MAX_LENGTH = 300

_UNAVAILABLE_MESSAGE = (
    "Provider integration is not available yet. "
    "Your key is stored securely and will be usable when the integration ships."
)


def normalize_label(label: str | None) -> str | None:
    """Strip edge whitespace; blank (incl. whitespace-only) collapses to None."""
    if label is None:
        return None
    stripped = label.strip()
    return stripped or None


def _validate_preconditions(provider: str, api_key: str, label: str | None) -> None:
    """Backend safety net — the schemas own input validation; this guards
    internal callers (same shape the schemas enforce stays a 400)."""
    if not is_supported_provider(provider):
        raise ValidationError(f"Unknown provider: {provider!r}.")
    if len(api_key) < _API_KEY_MIN_LENGTH or len(api_key) > _API_KEY_MAX_LENGTH:
        raise ValidationError(
            f"API key must be between {_API_KEY_MIN_LENGTH} and {_API_KEY_MAX_LENGTH} "
            "characters."
        )
    if label is not None and len(label) > _LABEL_MAX_LENGTH:
        raise ValidationError(f"Label must be at most {_LABEL_MAX_LENGTH} characters.")


def _not_found() -> NotFoundError:
    return NotFoundError("ai_provider")


def _encrypt_or_500(api_key: str) -> str:
    """Envelope-encrypt; a master-key/vault failure is OUR bug or outage —
    500 `internal_error` with a generic message, never the vault's internals."""
    try:
        ciphertext, _ = encrypt_secret(api_key)
        return ciphertext
    except VaultError:
        logger.exception("vault encryption failed")
        raise InternalError("Credential storage is temporarily unavailable.") from None


def _decrypt_or_500(ciphertext: str) -> str:
    try:
        return decrypt_secret(ciphertext)
    except VaultError:
        logger.exception("vault decryption failed")
        raise InternalError("Credential storage is temporarily unavailable.") from None


async def create_credential(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    provider: str,
    label: str | None,
    api_key: str,
) -> AICredential:
    """Store a credential: always enabled, never default.

    Stage 21 closes the live-proof remainder: CREATE validates the plaintext
    key with the provider adapter BEFORE storing it. Duplicate checks run
    before proof to avoid unnecessary outbound calls; the transactional insert
    re-checks them after proof to close races. No transaction spans provider
    network I/O.
    """
    label_n = normalize_label(label)
    _validate_preconditions(provider, api_key, label_n)
    repo = AICredentialRepository(session)
    fingerprint = fingerprint_secret(api_key)
    await _raise_create_conflicts(
        repo, owner_id=owner_id, provider=provider, fingerprint=fingerprint
    )
    # The SELECT preflight can autobegin a read transaction; close it before
    # provider I/O so no DB transaction spans the network call.
    await session.rollback()
    await _prove_create_key(provider=provider, api_key=api_key)
    return await _create_credential_row(
        session,
        owner_id=owner_id,
        provider=provider,
        label=label_n,
        api_key=api_key,
        fingerprint=fingerprint,
    )


async def _raise_create_conflicts(
    repo: AICredentialRepository,
    *,
    owner_id: uuid.UUID,
    provider: str,
    fingerprint: str,
) -> None:
    """Cheap preflight (and transactional re-check) for CREATE conflicts."""
    if await repo.get_enabled(owner_id=owner_id, provider=provider) is not None:
        raise ConflictError(
            "conflict",
            "An enabled credential already exists for this provider. "
            "Rotate its key or disable it first.",
        )
    if (
        await repo.get_by_fingerprint(
            owner_id=owner_id, provider=provider, key_fingerprint=fingerprint
        )
        is not None
    ):
        raise ConflictError(
            "conflict",
            "This API key is already stored for this provider. "
            "Use key rotation on the existing credential instead.",
        )


async def _prove_create_key(*, provider: str, api_key: str) -> None:
    """Creation-time proof-of-key (no storage on invalid/unreachable keys)."""
    adapter = resolve_adapter(provider)
    if adapter is None:  # defensive: all supported providers ship adapters since Stage 18
        raise ValidationError(_UNAVAILABLE_MESSAGE)
    try:
        result = await adapter.validate_credentials(api_key)
    except ProviderError as exc:
        logger.info("credential proof failed provider=%s code=%s", provider, exc.code)
        raise ValidationError(exc.user_message) from None
    if not result.ok:
        message = result.detail[:_ERROR_MAX_LENGTH] or "Provider rejected the API key."
        logger.info("credential proof rejected provider=%s", provider)
        raise ValidationError(message)


async def _create_credential_row(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    provider: str,
    label: str | None,
    api_key: str,
    fingerprint: str,
) -> AICredential:
    """Transactional insert after live proof; re-checks conflicts for races."""
    repo = AICredentialRepository(session)
    await _raise_create_conflicts(
        repo, owner_id=owner_id, provider=provider, fingerprint=fingerprint
    )
    try:
        row = await repo.create(
            owner_id=owner_id,
            provider=provider,
            label=label,
            encrypted_api_key=_encrypt_or_500(api_key),
            key_version=VAULT_VERSION,
            key_fingerprint=fingerprint,
            last4=api_key[-4:],
            last_test_status="ok",
            last_tested_at=utcnow(),
        )
    except IntegrityError:
        # Lost a create race: roll back, re-read, and report the CURRENT
        # state instead of the stale conflict the loser observed.
        await session.rollback()
        raced = await repo.get_enabled(owner_id=owner_id, provider=provider)
        raced_fingerprint = await repo.get_by_fingerprint(
            owner_id=owner_id, provider=provider, key_fingerprint=fingerprint
        )
        if raced is None and raced_fingerprint is None:  # pragma: no cover
            raise  # defensive; impossible post-conflict
        raise ConflictError(
            "conflict", "An enabled credential already exists for this provider."
        ) from None
    await session.commit()
    logger.info(
        "credential created credential_id=%s owner_id=%s provider=%s proof=ok",
        row.id,
        owner_id,
        provider,
    )
    return row


async def list_credentials(session: AsyncSession, *, owner_id: uuid.UUID) -> list[AICredential]:
    """Owned credentials, registry order then enabled-first then oldest."""
    rows = await AICredentialRepository(session).list_owned(owner_id=owner_id)
    return sorted(
        rows,
        key=lambda r: (PROVIDER_ORDER[r.provider], not r.is_enabled, r.created_at, r.id),
    )


async def get_credential(
    session: AsyncSession, *, owner_id: uuid.UUID, credential_id: uuid.UUID
) -> AICredential:
    """One owned credential (404 covers missing AND foreign — no oracle)."""
    row = await AICredentialRepository(session).get_owned(
        owner_id=owner_id, credential_id=credential_id
    )
    if row is None:
        raise _not_found()
    return row


@transactional
async def update_credential(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    credential_id: uuid.UUID,
    label: str | None = None,
    is_enabled: bool | None = None,
    is_default: bool | None = None,
    fallback_rank: int | None = None,
    label_provided: bool = False,
) -> AICredential:
    """Metadata update. `is_default=true` claims the owner's single default
    (clearing the previous holder in the same transaction; the partial unique
    index + `IntegrityError → 409` closes races). Disabling the default
    auto-clears its flag (a disabled default is meaningless); ASKING for the
    contradiction (disable + default together, or defaulting a disabled row)
    is `409 conflict` — a contradiction the caller should fix, not a
    validation slip. Re-enabling into an occupied provider is `409`."""
    repo = AICredentialRepository(session)
    row = await repo.get_owned(owner_id=owner_id, credential_id=credential_id)
    if row is None:
        raise _not_found()
    if label_provided:
        label_n = normalize_label(label)
        if label_n is not None and len(label_n) > _LABEL_MAX_LENGTH:
            raise ValidationError(f"Label must be at most {_LABEL_MAX_LENGTH} characters.")
        row.label = label_n
    if fallback_rank is not None:
        if fallback_rank < 0 or fallback_rank > _FALLBACK_RANK_MAX:
            raise ValidationError(f"Fallback rank must be between 0 and {_FALLBACK_RANK_MAX}.")
        row.fallback_rank = fallback_rank
    if is_enabled is False and is_default is True:
        raise ConflictError("conflict", "A credential cannot be the default while disabled.")
    if is_enabled is False and row.is_enabled:
        row.is_enabled = False
        row.is_default = False  # auto-clear: a disabled default is meaningless
    elif is_enabled is True and not row.is_enabled:
        if (
            await repo.get_enabled(owner_id=owner_id, provider=row.provider, exclude_id=row.id)
            is not None
        ):
            raise ConflictError(
                "conflict",
                "Another enabled credential already exists for this provider.",
            )
        row.is_enabled = True
    if is_default is True and not row.is_default:
        if not row.is_enabled:
            raise ConflictError("conflict", "A credential cannot be the default while disabled.")
        await repo.clear_default(owner_id=owner_id, exclude_id=row.id)
        row.is_default = True
    elif is_default is False:
        row.is_default = False
    try:
        # Flush inside the try: constraint races surface HERE (statement
        # time), not at commit — so we can still translate them to 409.
        await session.flush()
        await session.refresh(row)
    except IntegrityError:
        await session.rollback()
        raise ConflictError("conflict", "Concurrent update conflict; please retry.") from None
    logger.info(
        "credential updated credential_id=%s owner_id=%s provider=%s",
        row.id,
        owner_id,
        row.provider,
    )
    return row


@transactional
async def rotate_key(
    session: AsyncSession, *, owner_id: uuid.UUID, credential_id: uuid.UUID, api_key: str
) -> AICredential:
    """Replace stored key material (new ciphertext; test verdict cleared —
    the new key is unproven). Re-saving the row's CURRENT key is a harmless
    no-op success; key material living on ANOTHER row is `409`."""
    if len(api_key) < _API_KEY_MIN_LENGTH or len(api_key) > _API_KEY_MAX_LENGTH:
        raise ValidationError(
            f"API key must be between {_API_KEY_MIN_LENGTH} and {_API_KEY_MAX_LENGTH} "
            "characters."
        )
    repo = AICredentialRepository(session)
    row = await repo.get_owned(owner_id=owner_id, credential_id=credential_id)
    if row is None:
        raise _not_found()
    fingerprint = fingerprint_secret(api_key)
    if (
        await repo.get_by_fingerprint(
            owner_id=owner_id,
            provider=row.provider,
            key_fingerprint=fingerprint,
            exclude_id=row.id,
        )
        is not None
    ):
        raise ConflictError("conflict", "This API key is already stored on another credential.")
    try:
        row.encrypted_api_key = _encrypt_or_500(api_key)
        row.key_fingerprint = fingerprint
        row.key_version = VAULT_VERSION
        row.last4 = api_key[-4:]
        row.last_test_status = None
        row.last_tested_at = None
        await session.flush()
        await session.refresh(row)
    except IntegrityError:
        await session.rollback()
        raise ConflictError("conflict", "Concurrent update conflict; please retry.") from None
    logger.info(
        "credential key rotated credential_id=%s owner_id=%s provider=%s",
        row.id,
        owner_id,
        row.provider,
    )
    return row


@transactional
async def delete_credential(
    session: AsyncSession, *, owner_id: uuid.UUID, credential_id: uuid.UUID
) -> None:
    """Delete an owned credential (ciphertext gone; 404 for missing/foreign)."""
    repo = AICredentialRepository(session)
    row = await repo.get_owned(owner_id=owner_id, credential_id=credential_id)
    if row is None:
        raise _not_found()
    provider = row.provider
    await repo.delete(row)
    logger.info(
        "credential deleted credential_id=%s owner_id=%s provider=%s",
        credential_id,
        owner_id,
        provider,
    )


async def test_credential(
    session: AsyncSession, *, owner_id: uuid.UUID, credential_id: uuid.UUID
) -> tuple[bool, list[str], int, str | None]:
    """Live-check a credential OUTSIDE any transaction (no txn may span
    network I/O) and record the verdict in a short follow-up transaction.

    A credential whose provider has no adapter yet (defensive — all six
    ship adapters since Stage 18) deterministically reports unavailable:
    200 `{ok: false}` with a ship-date message, `last_test_*` untouched. A
    missing master key / broken vault is OUR outage → 500; a
    disabled credential tests fine (the check validates key material, not
    routing state). Returns (ok, models, latency_ms, error)."""
    row = await AICredentialRepository(session).get_owned(
        owner_id=owner_id, credential_id=credential_id
    )
    if row is None:
        raise _not_found()
    adapter = resolve_adapter(row.provider)
    if adapter is None:
        logger.info(
            "credential test unavailable credential_id=%s owner_id=%s provider=%s",
            row.id,
            owner_id,
            row.provider,
        )
        return False, [], 0, _UNAVAILABLE_MESSAGE
    api_key = _decrypt_or_500(row.encrypted_api_key)
    started = perf_counter()
    try:
        health = await adapter.health_check(api_key)
        if health.ok:
            # Third-party-adjacent text: cap count + width so a hostile model
            # list cannot bloat the response (shape stays ours, not theirs).
            models = [model[:128] for model in await adapter.list_models(api_key)][:50]
            ok: bool = True
            error: str | None = None
        else:
            models = []
            ok = False
            error = health.detail[:_ERROR_MAX_LENGTH] or "Provider check failed."
    except ProviderError as exc:
        # The ONLY sanctioned adapter failure (user-safe by ABC contract) —
        # anything else is an adapter bug and correctly 500s unhandled.
        models = []
        ok = False
        error = exc.user_message[:_ERROR_MAX_LENGTH]
    latency_ms = int((perf_counter() - started) * 1000)
    await _record_test_result(session, credential_id=row.id, ok=ok, tested_at=utcnow())
    logger.info(
        "credential tested credential_id=%s owner_id=%s provider=%s ok=%s latency_ms=%s",
        row.id,
        owner_id,
        row.provider,
        ok,
        latency_ms,
    )
    return ok, models, latency_ms, error


@transactional
async def _record_test_result(
    session: AsyncSession, *, credential_id: uuid.UUID, ok: bool, tested_at: datetime
) -> None:
    await AICredentialRepository(session).record_test_result(
        credential_id=credential_id,
        status="ok" if ok else "failed",
        tested_at=tested_at,
    )
