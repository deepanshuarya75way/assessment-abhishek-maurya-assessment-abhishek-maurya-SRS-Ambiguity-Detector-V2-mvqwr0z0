"""Auth rate limiting: single-process token buckets (Stage 04 foundation).

Contract (SECURITY_SPEC §7): sensitive ops get per-key buckets with 429 +
Retry-After. The DISTRIBUTED store lands in Stage 22 — until then these buckets
are exact behind one worker and fail OPEN (N workers ≈ N× budget each holding a
full bucket). Env: RATE_LIMIT_ENABLED, RATE_LIMIT_AUTH_PER_MINUTE (default
budget), RATE_LIMIT_ANALYSIS_PER_MINUTE (analysis creation, Stage 06).

Keys are `{endpoint}:{client_socket_ip}` (auth, anonymous) or
`{resource}:{endpoint}:user:{user_id}` (authenticated resources) — never trust
X-Forwarded-For here.
Bucket math need not be lock-step exact — worst case is slight over/under
counting, which is acceptable for a limiter (fail-open direction preferred).
"""

import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger
from app.exceptions import RateLimitedError

_MAX_BUCKETS = 100_000  # memory cap; overflow clears (fail open, documented)


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


_buckets: dict[str, _Bucket] = {}
logger = get_logger(__name__)


def _bucket_category(key: str) -> str:
    parts = key.split(":")
    if parts and parts[0] == "auth" and len(parts) >= 2:
        return f"auth:{parts[1]}"
    return parts[0] if parts else "unknown"


def reset_rate_limiter() -> None:
    """Clear all buckets (tests only — production never calls this)."""
    _buckets.clear()


def check_rate_limit(key: str, limit: int | None = None) -> None:
    """Consume one token from `key`'s per-minute bucket; raise 429 when empty.

    `limit` overrides the per-minute budget for this bucket (callers resolve it
    per-request from settings, so tests can retune via env); `None` keeps the
    auth default (`RATE_LIMIT_AUTH_PER_MINUTE`).
    """
    settings = get_settings()
    if not settings.RATE_LIMIT_ENABLED:
        return
    budget = settings.RATE_LIMIT_AUTH_PER_MINUTE if limit is None else limit
    limit = max(1, budget)
    now = time.monotonic()
    bucket = _buckets.get(key)
    if bucket is None:
        if len(_buckets) >= _MAX_BUCKETS:
            _buckets.clear()  # fail open under key-spray; see module docstring
        _buckets[key] = _Bucket(tokens=float(limit - 1), updated_at=now)
        return
    elapsed = now - bucket.updated_at
    bucket.tokens = min(float(limit), bucket.tokens + elapsed * (limit / 60.0))
    bucket.updated_at = now
    if bucket.tokens < 1.0:
        retry_after = int((1.0 - bucket.tokens) * (60.0 / limit)) + 1
        logger.warning(
            "rate limit exceeded bucket=%s retry_after=%d",
            _bucket_category(key),
            retry_after,
            extra={"rate_limit_bucket": _bucket_category(key), "error_code": "rate_limited"},
        )
        raise RateLimitedError(max(1, retry_after))
    bucket.tokens -= 1.0
