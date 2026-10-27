"""Structured logging with aggressive secret redaction.

``RedactingFilter`` scrubs sensitive key=value pairs and bearer tokens from every
record. The root handler emits JSON lines with an allowlist of low-cardinality
operational fields so logs are machine-readable without becoming a privacy leak.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_REDACTED = "***REDACTED***"

_KEY_ALTERNATION = (
    r"api[_-]?key|password|passwd|pwd|secret|token|cookie"
    r"|set-cookie|access[_-]?token|refresh[_-]?token|client[_-]?secret"
)

_AUTH_HEADER_PATTERN = re.compile(
    r"(?i)([\"']?authorization[\"']?)(\s*[:=]\s*)(Bearer\s+)?\S+(?:\s+\S+)?"
)
_PAIR_PATTERN = re.compile(
    rf"(?i)([\"']?)({_KEY_ALTERNATION})\1(\s*[:=]\s*)([\"']?)(Bearer\s+)?([^\s,;\"'}}\]]+)\4"
)
_BEARER_PATTERN = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*")

_STRUCTURED_FIELD_ALLOWLIST = {
    "request_id",
    "http_method",
    "http_path",
    "http_route",
    "status_code",
    "duration_ms",
    "error_code",
    "exception_class",
    "analysis_stage",
    "document_stage",
    "ai_provider",
    "ai_model",
    "retry_count",
    "storage_operation",
    "database_operation",
    "rate_limit_bucket",
    "email_template",
    "email_provider",
}


def _scrub_pair(match: re.Match[str]) -> str:
    """Rebuild a key=value match with the value redacted (quotes/scheme preserved)."""
    key_quote, key, sep, val_quote, bearer, _value = match.groups()
    scheme = "Bearer " if bearer else ""
    return f"{key_quote}{key}{key_quote}{sep}{val_quote}{scheme}{_REDACTED}{val_quote}"


def redact(text: str) -> str:
    """Redact secret-looking fragments from an already-rendered string."""
    text = _AUTH_HEADER_PATTERN.sub(r"\1\2\3" + _REDACTED, text)
    text = _PAIR_PATTERN.sub(_scrub_pair, text)
    text = _BEARER_PATTERN.sub(r"\1" + _REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from the formatted record message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - never break logging itself
            return True
        scrubbed = redact(rendered)
        if scrubbed != rendered:
            record.msg = scrubbed
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """JSON-line formatter with explicit extra-field allowlist."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
        }
        for field in _STRUCTURED_FIELD_ALLOWLIST:
            if field == "request_id":
                continue
            if hasattr(record, field):
                value = getattr(record, field)
                if isinstance(value, str):
                    payload[field] = redact(value)
                elif isinstance(value, int | float | bool) or value is None:
                    payload[field] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_class"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install a single stdout handler with redaction and structured formatting."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in root.handlers:
        handler.addFilter(RedactingFilter())
        handler.setFormatter(JsonFormatter())
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (redaction is applied at the handler level)."""
    return logging.getLogger(name)
