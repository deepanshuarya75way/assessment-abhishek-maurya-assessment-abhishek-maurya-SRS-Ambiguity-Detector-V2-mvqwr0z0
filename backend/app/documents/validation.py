"""Upload validation pipeline (Stage 08, SECURITY_SPEC §5).

Pure functions over staged bytes — no I/O beyond reading the staged temp file,
no framework imports. Order is deliberate (cheapest, most decisive checks
first)::

    byte_size → filename → extension → declared MIME → magic bytes →
    format-specific structure (OOXML members / PDF header / TXT binary sniff)

Anything failing here is a 4xx: the file is rejected BEFORE any parsing, and
(as everywhere else) nothing is persisted on rejection. Malformed-but-correctly
-typed files fail LATER, at extraction (422) — the 400/422 boundary is "is it
what it claims to be" vs "can it be read".
"""

from __future__ import annotations

import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    InvalidFilenameError,
    UnsupportedFileTypeError,
)

FileType = Literal["pdf", "docx", "txt"]

# Extension → verified type (lowercased suffix AFTER sanitization; the ONLY
# suffix consulted — `evil.pdf.exe` ends in `.exe` and is rejected).
EXTENSION_TYPES: dict[str, FileType] = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}

# Canonical MIME per verified type — this DETECTED value is what we store,
# never the client-declared string.
DETECTED_MIME: dict[FileType, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}

# The absence of a claim is not a conflict: generic senders (curl, some
# browsers) declare octet-stream. Tolerated ONLY when extension + content
# verify; anything else must match the expected MIME exactly.
GENERIC_MIME = "application/octet-stream"

# Mirrors documents.filename VARCHAR(255).
FILENAME_MAX_LENGTH = 255

# OOXML proof: a real .docx is a ZIP containing these (checked via the central
# directory — nothing is extracted to validate structure).
DOCX_REQUIRED_MEMBERS = frozenset({"[Content_Types].xml", "word/document.xml"})

# Zip-bomb pre-guards (metadata only — no decompression to decide).
DOCX_MAX_MEMBERS = 2000
DOCX_MAX_INFLATED_BYTES = 50_000_000

# PDF header tolerance: ASCII whitespace + UTF-8 BOM before %PDF- (broken
# producers exist; pypdf itself is stricter — genuinely malformed files still
# fail at extraction with 422).
_PDF_MAGIC = b"%PDF-"
_UTF8_BOM = b"\xef\xbb\xbf"
_ASCII_WS = b" \t\r\n\x0b\x0c"
_DOCX_MAGIC = b"PK\x03\x04"  # local file header (not empty/spanned archives)


@dataclass(frozen=True)
class ValidatedUpload:
    """A staged file that proved to be what it claims. `mime_type` is the
    server-detected canonical MIME; `filename` is the sanitized display name
    (metadata only — NEVER a path)."""

    file_type: FileType
    mime_type: str
    filename: str
    byte_size: int
    sha256: str


def sanitize_filename(raw: object) -> str:
    """Reduce an untrusted upload name to a safe display string.

    Neutralizes (by construction, not blocklist): path traversal, absolute
    paths, Windows separators/drives, NUL bytes, control characters, and
    invisible trailing dots/spaces. Raises only when nothing usable remains.
    """
    if not isinstance(raw, str):
        raise InvalidFilenameError()
    # Last segment on BOTH separators: `a/b`, `..\\..\\x`, `C:\\y` all collapse
    # to a bare name (display-only — this string never touches the filesystem).
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    # Drop NUL + C0/C1 controls + DEL (display + JSON + DB safe).
    name = "".join(char for char in name if not (ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F))
    name = unicodedata.normalize("NFC", name).strip().rstrip(".")
    if not name:
        raise InvalidFilenameError()
    if len(name) > FILENAME_MAX_LENGTH:
        raise InvalidFilenameError()
    return name


def _extension_of(filename: str) -> str:
    _, dot, suffix = filename.rpartition(".")
    if not dot or not suffix:
        raise UnsupportedFileTypeError()
    return f".{suffix.lower()}"


def _check_declared_mime(file_type: FileType, declared: object) -> None:
    """The declared MIME must AGREE with the extension — exact match or the
    generic absence-of-claim. A conflicting claim (`.pdf` as `image/png`) is
    spoofing-shaped and rejected."""
    if not isinstance(declared, str):
        raise UnsupportedFileTypeError()
    normalized = declared.split(";", 1)[0].strip().lower()
    if normalized in (DETECTED_MIME[file_type], GENERIC_MIME):
        return
    raise UnsupportedFileTypeError()


def _check_pdf_magic(head: bytes) -> None:
    probe = head.lstrip(_ASCII_WS)
    if probe.startswith(_UTF8_BOM):
        probe = probe[len(_UTF8_BOM) :].lstrip(_ASCII_WS)
    if not probe.startswith(_PDF_MAGIC):
        raise UnsupportedFileTypeError()


def _check_docx_structure(path: Path) -> None:
    """Prove OOXML-ness from ZIP metadata (no extraction, no decompression):
    valid ZIP + required members + member-count/inflated-size bomb guards."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.namelist()
            inflated = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError):
        raise UnsupportedFileTypeError() from None
    if len(members) > DOCX_MAX_MEMBERS:
        raise FileTooLargeError(DOCX_MAX_MEMBERS, reason="docx_members")
    if not DOCX_REQUIRED_MEMBERS.issubset(members):
        # A valid ZIP that is not OOXML (renamed .zip etc.) — not a .docx.
        raise UnsupportedFileTypeError()
    if inflated > DOCX_MAX_INFLATED_BYTES:
        raise FileTooLargeError(DOCX_MAX_INFLATED_BYTES, reason="docx_inflated_size")


def _check_txt_binary_sniff(path: Path) -> None:
    """Reject NUL-bearing `.txt` (binary renamed to .txt). Text never contains
    NUL; binaries almost always do — cheap, decisive, documented."""
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            if b"\x00" in chunk:
                raise UnsupportedFileTypeError()


def validate_staged_file(
    path: Path,
    *,
    filename: object,
    declared_mime: object,
    byte_size: int,
    sha256: str,
) -> ValidatedUpload:
    """Run the full validation pipeline over a staged temp file (raises the
    4xx AppError for the first failing gate)."""
    if byte_size <= 0:
        raise EmptyFileError()
    clean_name = sanitize_filename(filename)
    file_type = EXTENSION_TYPES.get(_extension_of(clean_name))
    if file_type is None:
        raise UnsupportedFileTypeError()
    _check_declared_mime(file_type, declared_mime)
    with open(path, "rb") as handle:
        head = handle.read(1024)
    if file_type == "pdf":
        _check_pdf_magic(head)
    elif file_type == "docx":
        if not head.startswith(_DOCX_MAGIC):
            raise UnsupportedFileTypeError()
        _check_docx_structure(path)
    else:
        _check_txt_binary_sniff(path)
    return ValidatedUpload(
        file_type=file_type,
        mime_type=DETECTED_MIME[file_type],
        filename=clean_name,
        byte_size=byte_size,
        sha256=sha256,
    )
