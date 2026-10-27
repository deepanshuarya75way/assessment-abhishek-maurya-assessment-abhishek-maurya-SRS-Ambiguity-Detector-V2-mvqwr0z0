"""AI output hygiene (AI_PROVIDER_SPEC §3: UNTRUSTED until sanitized).

Adapters sanitize every model output BEFORE building `AITextResult` (so the
Pydantic `max_length` caps never raise on provider text) and the
enhancement service persists only sanitized text. Rendering stays safe by
construction: React escapes text by default, and nothing here is ever
interpreted as markup or instructions.
"""

import re

# Spec §3: constrained text out (≤8 000 chars, truncated with marker).
AI_TEXT_MAX_CHARS = 8000
_TRUNCATION_MARKER = "\n…[truncated]"

# Control characters with no business in stored prose: NUL-BEL range minus
# \t (0x09) and \n (0x0a), which models legitimately emit. \r is normalized
# to \n first (CRLF → LF) so Windows-style outputs don't smuggle carriage
# returns into stored text.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_ai_text(text: str, *, max_chars: int = AI_TEXT_MAX_CHARS) -> str:
    """Normalize line endings, strip control chars + edge whitespace, cap length.

    Pure: the same provider text always sanitizes identically. The marker
    keeps truncation HONEST — readers can tell output was cut.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _CONTROL_CHARS_RE.sub("", normalized).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
