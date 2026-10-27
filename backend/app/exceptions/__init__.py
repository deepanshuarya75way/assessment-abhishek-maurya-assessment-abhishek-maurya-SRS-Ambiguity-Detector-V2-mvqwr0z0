"""Application errors → uniform envelope (the project contract).

Services raise these; main.py maps them to HTTP. Messages are user-safe by
construction — never interpolate SQL, DSNs, or raw driver text into them.
"""

from __future__ import annotations


class AppError(Exception):
    """Base: stable machine code + safe message + HTTP status + optional details."""

    def __init__(
        self, code: str, message: str, status_code: int = 500, details: object = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    """404 with a per-resource code. Doubles as the IDOR response (no oracle)."""

    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource}_not_found", "The requested resource was not found.", 404)


class ConflictError(AppError):
    """409 — duplicate / state conflict (code + message supplied by the service)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


class UnauthorizedError(AppError):
    """401 — missing/invalid session (wired to auth in Stage 04)."""

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__("unauthenticated", message, 401)


class ForbiddenError(AppError):
    """403 — authenticated but not allowed (ownership checks from Stage 04)."""

    def __init__(self, message: str = "You do not have access to this resource.") -> None:
        super().__init__("forbidden", message, 403)


class InvalidCredentialsError(AppError):
    """401 — bad email/password (identical message for unknown email: no oracle)."""

    def __init__(self) -> None:
        super().__init__("invalid_credentials", "Invalid email or password.", 401)


class AccountDisabledError(AppError):
    """403 — password correct but account deactivated (post-auth, no oracle)."""

    def __init__(self) -> None:
        super().__init__("account_disabled", "This account has been disabled.", 403)


class InvalidTokenError(AppError):
    """400 — token unknown/expired/consumed. Honest errors are safe here: 256-bit
    tokens are not enumerable, so there is no oracle."""

    def __init__(self, message: str = "This link is invalid or has expired.") -> None:
        super().__init__("invalid_token", message, 400)


class WeakPasswordError(AppError):
    """400 — password fails policy beyond length (denylist)."""

    def __init__(self, message: str = "This password is too easy to guess.") -> None:
        super().__init__("password_too_weak", message, 400)


class RateLimitedError(AppError):
    """429 — auth rate bucket exhausted (main.py adds the Retry-After header)."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate_limited", "Too many attempts. Please try again shortly.", 429)
        self.retry_after_seconds = retry_after_seconds


class CurrentPasswordError(AppError):
    """400 — wrong current password on change (authenticated: honesty is safe)."""

    def __init__(self) -> None:
        super().__init__("current_password_incorrect", "Current password is incorrect.", 400)


class NoRequirementsDetectedError(AppError):
    """400 — TEXT input yielded zero segments (blank or signal-less prose)."""

    def __init__(
        self, message: str = "No requirements could be detected in the provided text."
    ) -> None:
        super().__init__("no_requirements_detected", message, 400)


class TextTooLargeError(AppError):
    """400 — segmentation produced more requirements than the per-analysis cap
    (API_CONTRACT §4.3: refuse with counts, never silently truncate)."""

    def __init__(self, requirements_found: int, max_requirements: int) -> None:
        super().__init__(
            "text_too_large",
            "The input produced more requirements than a single analysis can hold.",
            400,
            details={
                "requirements_found": requirements_found,
                "max_requirements": max_requirements,
            },
        )


class DocumentAnalysisUnavailableError(AppError):
    """400 — `document_id` on POST /analysis. Stage 08 analyzes uploaded FILES
    (POST /documents/upload); re-analyzing a stored document BY ID is still
    unavailable (no retrieval pipeline yet)."""

    def __init__(
        self,
        message: str = "Analyzing a saved document by id is not available yet.",
    ) -> None:
        super().__init__("document_analysis_unavailable", message, 400)


class UnsupportedFileTypeError(AppError):
    """400 — extension / declared MIME / magic bytes disagree, or the type is
    outside pdf/docx/txt. The file is not what it claims to be (or not
    something we accept) — rejected before any parsing."""

    def __init__(
        self, message: str = "The uploaded file is not a supported document type."
    ) -> None:
        super().__init__("unsupported_file_type", message, 400)


class InvalidFilenameError(AppError):
    """400 — filename missing, empty after sanitization, or over the length
    cap. Display names are metadata only (never paths), but they must exist."""

    def __init__(self, message: str = "The uploaded filename is missing or invalid.") -> None:
        super().__init__("invalid_filename", message, 400)


class FileTooLargeError(AppError):
    """400 — a size/complexity budget was breached: streamed `byte_size`,
    `pdf_pages`, or DOCX `docx_members`/`docx_inflated_size`. `details`
    names the reason + the breached limit — never the file's content."""

    def __init__(self, limit: int, reason: str = "byte_size") -> None:
        super().__init__(
            "file_too_large",
            "The uploaded file exceeds the size limit.",
            400,
            details={"reason": reason, "limit": limit},
        )


class ExtractedTextTooLargeError(AppError):
    """400 — extraction output passed MAX_EXTRACTED_TEXT_CHARS. Aborted
    mid-extraction: nothing downstream (segmentation, analysis) ever runs."""

    def __init__(self, max_chars: int) -> None:
        super().__init__(
            "extracted_text_too_large",
            "The document contains more text than a single analysis can hold.",
            400,
            details={"max_chars": max_chars},
        )


class EmptyFileError(AppError):
    """400 — zero bytes uploaded. Distinct from `no_extractable_text` (which
    means: bytes existed, but no text could be read from them)."""

    def __init__(self, message: str = "The uploaded file is empty.") -> None:
        super().__init__("empty_file", message, 400)


class TooManyFilesError(AppError):
    """400 — more `file` parts than MAX_FILES_PER_REQUEST (sync pipeline
    analyzes one file per call)."""

    def __init__(self, max_files: int) -> None:
        super().__init__(
            "too_many_files",
            "Upload one file at a time.",
            400,
            details={"max_files": max_files},
        )


class ExtractionFailedError(AppError):
    """422 — the file passed type checks but the parser could not read it
    (malformed PDF/DOCX, undecodable text). Parser internals stay server-side."""

    def __init__(self, message: str = "The document could not be read.") -> None:
        super().__init__("extraction_failed", message, 422)


class NoExtractableTextError(AppError):
    """422 — parsed fine, but zero usable text (image-only/scanned PDF, empty
    DOCX/TXT). Honest, not silent: OCR does not exist (future roadmap)."""

    def __init__(self, message: str = "No extractable text was found in this document.") -> None:
        super().__init__("no_extractable_text", message, 422)


class DocumentProcessingTimeoutError(AppError):
    """503 — validate+extract exceeded DOCUMENT_PROCESSING_TIMEOUT_SECONDS.
    Retryable: the temp file was cleaned up; nothing was persisted."""

    def __init__(self, message: str = "Document processing took too long.") -> None:
        super().__init__("document_processing_timeout", message, 503)


class ValidationError(AppError):
    """400 — service-level contract misuse (same code the schema handler
    emits for malformed bodies). Schemas own HTTP input validation; this
    guards service preconditions for non-HTTP/internal callers."""

    def __init__(self, message: str) -> None:
        super().__init__("validation_error", message, 400)


class InternalError(AppError):
    """500 — explicit server-side failure (e.g. vault misconfigured).

    Preferred over relying on the unhandled-exception path when the service
    KNOWS the failure mode: same wire shape, clearer intent. Messages MUST
    stay generic — never interpolate secrets, ciphertext, or config values.
    """

    def __init__(self, message: str = "Something went wrong.") -> None:
        super().__init__("internal_error", message, 500)
