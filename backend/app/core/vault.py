"""Fernet envelope for per-user provider API keys (SECURITY_SPEC §4, ADR-006).

Ciphertext is stored `vN:`-prefixed (AES-128-CBC + HMAC-SHA256 via Fernet);
the master key comes ONLY from `ENCRYPTION_MASTER_KEY` (env, validated at
boot — absent is legal because AI is optional, malformed fails closed).
Decryption happens in backend memory at call time; NOTHING here ever logs,
returns, or raises with secret material — `VaultError` messages name the
failure category only. Rotation beyond v1 is a future runbook: the version
dispatch below is the seam (unknown versions fail safely, never as
plaintext).
"""

import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

VAULT_VERSION = 1
_CIPHERTEXT_PREFIX = f"v{VAULT_VERSION}:"


class VaultError(Exception):
    """Sanitized vault failure (services map it to `500 internal_error`)."""


def _master_fernet(version: int) -> Fernet:
    if version != VAULT_VERSION:
        raise VaultError(f"unsupported vault key version: v{version}")
    key = get_settings().ENCRYPTION_MASTER_KEY
    if not key:
        raise VaultError("credential vault is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except ValueError:
        raise VaultError("credential vault is misconfigured") from None


def encrypt_secret(plaintext: str) -> tuple[str, int]:
    """Encrypt one secret → (`vN:`-prefixed ciphertext, key version)."""
    token = _master_fernet(VAULT_VERSION).encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_CIPHERTEXT_PREFIX}{token}", VAULT_VERSION


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt `vN:` ciphertext in backend memory (wrong key / tampered /
    truncated / unknown version → `VaultError`, never partial output)."""
    prefix, separator, token = ciphertext.partition(":")
    if not separator or not prefix.startswith("v") or not prefix[1:].isdigit():
        raise VaultError("credential ciphertext is malformed")
    fernet = _master_fernet(int(prefix[1:]))
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        raise VaultError("credential cannot be decrypted") from None


def fingerprint_secret(plaintext: str) -> str:
    """Non-reversible same-key check (`sha256(key)[0:16]` per schema §3.6)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()[:16]
