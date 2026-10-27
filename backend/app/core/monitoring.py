"""Privacy-first monitoring integration (Stage 24).

Sentry is optional infrastructure: when SENTRY_DSN is unset, all helpers are
no-ops. When enabled, the before_send hook aggressively minimizes request and
exception data so monitoring cannot become a copy of user SRS text, upload
contents, AI prompts/responses, credentials, cookies, or tokens.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.types import Event

from app import __version__
from app.core.config import Settings
from app.core.logging import get_logger, redact

logger = get_logger(__name__)

_FILTERED = "[Filtered]"
_MAX_STRING_CHARS = 512

_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "csrf",
    "api_key",
    "apikey",
    "key",
    "credential",
    "encrypted_api_key",
    "refresh",
    "verification",
    "reset",
    "prompt",
    "response",
    "source_text",
    "requirement_text",
    "document_content",
    "file_bytes",
    "storage_path",
)

_DROP_REQUEST_FIELDS = {"data", "body", "cookies", "query_string", "env"}
_ALLOWED_CONTEXT_KEYS = {
    "request_id",
    "component",
    "operation",
    "error_code",
    "exception_class",
    "http_route",
    "http_method",
    "status_code",
    "analysis_stage",
    "document_stage",
    "ai_provider",
    "ai_model",
    "storage_operation",
    "database_operation",
    "rate_limit_bucket",
}


def _is_sensitive_key(key: object) -> bool:
    key_l = str(key).lower().replace("-", "_")
    return any(fragment in key_l for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _truncate(value: str) -> str:
    safe = redact(value)
    if len(safe) <= _MAX_STRING_CHARS:
        return safe
    return f"{safe[:_MAX_STRING_CHARS]}…[truncated]"


def _strip_query(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return _FILTERED
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def scrub_value(value: Any) -> Any:
    """Recursively remove sensitive fields and cap arbitrary strings.

    This intentionally favors over-redaction; observability fields are re-added
    explicitly through low-cardinality tags/contexts rather than trusting SDK
    defaults or exception messages.
    """
    if isinstance(value, Mapping):
        scrubbed: dict[str, Any] = {}
        for key, child in value.items():
            key_s = str(key)
            if _is_sensitive_key(key_s):
                scrubbed[key_s] = _FILTERED
            else:
                scrubbed[key_s] = scrub_value(child)
        return scrubbed
    if isinstance(value, list):
        return [scrub_value(item) for item in value[:50]]
    if isinstance(value, tuple):
        return tuple(scrub_value(item) for item in value[:50])
    if isinstance(value, str):
        return _truncate(value)
    return value


def _sanitize_request(request: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in request.items():
        key_l = key.lower()
        if key_l in _DROP_REQUEST_FIELDS or _is_sensitive_key(key_l):
            safe[key] = _FILTERED
            continue
        if key_l == "url" and isinstance(value, str):
            safe[key] = _strip_query(value)
            continue
        if key_l == "headers" and isinstance(value, Mapping):
            safe[key] = scrub_value(value)
            continue
        safe[key] = scrub_value(value)
    return safe


def before_send(event: Event, hint: dict[str, Any]) -> Event | None:
    """Sentry scrubber used by backend tests and runtime initialization."""
    _ = hint
    if isinstance(event.get("request"), dict):
        event["request"] = _sanitize_request(event["request"])
    if isinstance(event.get("extra"), dict):
        event["extra"] = scrub_value(event["extra"])
    if isinstance(event.get("contexts"), dict):
        event["contexts"] = scrub_value(event["contexts"])
    if isinstance(event.get("breadcrumbs"), dict):
        event["breadcrumbs"] = scrub_value(event["breadcrumbs"])

    # Exception messages may contain user-controlled content from third-party
    # libraries. Keep type/stack, redact arbitrary value strings.
    exception = event.get("exception")
    if isinstance(exception, dict) and isinstance(exception.get("values"), list):
        for item in exception["values"]:
            if isinstance(item, dict) and "value" in item:
                item["value"] = "details redacted"

    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        if isinstance(logentry.get("message"), str):
            logentry["message"] = _truncate(logentry["message"])
        if isinstance(logentry.get("formatted"), str):
            logentry["formatted"] = _truncate(logentry["formatted"])
    return event


def init_monitoring(settings: Settings) -> None:
    """Initialize Sentry when configured; never fail application startup."""
    if not settings.SENTRY_DSN:
        return
    try:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT or settings.APP_ENV,
            release=settings.SENTRY_RELEASE or __version__,
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            before_send=before_send,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                # Do not promote logs/breadcrumbs automatically; our explicit
                # capture helpers attach only allowlisted context.
                LoggingIntegration(level=None, event_level=None),
            ],
        )
        logger.info("monitoring initialized provider=sentry environment=%s", settings.APP_ENV)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.warning("monitoring initialization failed exc=%s", type(exc).__name__)


def _safe_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {}
    return {
        key: scrub_value(value)
        for key, value in context.items()
        if key in _ALLOWED_CONTEXT_KEYS and not _is_sensitive_key(key)
    }


def _capture_exception(exc: BaseException) -> str | None:
    return sentry_sdk.capture_exception(exc)


SentryLevel = Literal["fatal", "critical", "error", "warning", "info", "debug"]


def _capture_message(message: str, *, level: SentryLevel = "info") -> str | None:
    return sentry_sdk.capture_message(message, level=level)


def capture_exception(
    exc: BaseException,
    *,
    request_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Capture an unexpected exception with allowlisted low-cardinality context."""
    try:
        with sentry_sdk.new_scope() as scope:
            if request_id:
                scope.set_tag("request_id", request_id)
            for key, value in _safe_context(context).items():
                scope.set_tag(key, value) if isinstance(value, str | int | float | bool) else None
            _capture_exception(exc)
    except Exception as capture_exc:  # pragma: no cover - monitoring must not break requests
        logger.debug("monitoring capture_exception failed exc=%s", type(capture_exc).__name__)


def capture_message(
    message: str,
    *,
    level: SentryLevel = "info",
    context: Mapping[str, Any] | None = None,
) -> None:
    """Capture a sanitized operational event without attaching raw exception data."""
    try:
        with sentry_sdk.new_scope() as scope:
            for key, value in _safe_context(context).items():
                scope.set_tag(key, value) if isinstance(value, str | int | float | bool) else None
            _capture_message(_truncate(message), level=level)
    except Exception as capture_exc:  # pragma: no cover
        logger.debug("monitoring capture_message failed exc=%s", type(capture_exc).__name__)
