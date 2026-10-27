"""Bounded text extraction (Stage 08): staged file → plain text.

One `DocumentExtractor` per verified file type, selected by the VALIDATED type
(never the extension alone). Every extractor enforces `max_chars` DURING
accumulation — a malicious file cannot balloon memory before the cap trips —
and returns text the analysis pipeline consumes unmodified
(`segmentation.normalize_text` → segment → engine).

Safety posture (SECURITY_SPEC §5): parsers only ever READ (pypdf ignores
embedded JS/actions; python-docx never touches macros — `vbaProject.bin`, if
present, is simply never opened); nothing extracted executes; `\\x00` is
stripped everywhere (Postgres TEXT rejects it); parser tracebacks map to
`extraction_failed` (details stay server-side — log ids/counts only).

What is NOT here: OCR (image-only PDFs honestly 422), `.doc`/`.docm`/ODT/RTF,
auto-number recovery (Word numbering lives outside paragraph text — literal
numbers only), headers/footers (body + tables only, documented).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.documents.validation import FileType
from app.exceptions import (
    ExtractedTextTooLargeError,
    ExtractionFailedError,
    FileTooLargeError,
    NoExtractableTextError,
)

# Parser micro-limits (centralized HERE — headline budgets live in Settings).
# 500 pages × dense text still fits MAX_EXTRACTED_TEXT_CHARS comfortably; the
# cap exists to bound CPU (per-page layout analysis), not output.
PDF_MAX_PAGES = 500


@dataclass(frozen=True)
class ExtractedDocument:
    """Extraction result. `text` is content-complete (never silently cut —
    over-budget input raises instead); `pages`/`encoding` are honest
    traceability metadata (None when the format has no such concept)."""

    text: str
    file_type: FileType
    pages: int | None = None
    encoding: str | None = None


class DocumentExtractor(Protocol):
    """One verified file type's reader. `path` is a staged temp file that
    ALREADY passed validation; `max_chars` is the hard output budget."""

    file_type: FileType

    def extract(self, path: Path, *, max_chars: int) -> ExtractedDocument: ...


def _clean_text(raw: str) -> str:
    """Make parser output pipeline-safe: \\r\\n/\\r → \\n (uniform breaks for
    segmentation), drop NUL (Postgres TEXT rejects `\\x00`). Nothing else is
    altered — offsets/claims downstream reflect this exact text."""
    return raw.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


class _CharBudget:
    """Running output accumulator that raises the INSTANT the cap trips —
    no over-read, no silent truncation."""

    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars
        self._parts: list[str] = []
        self._total = 0

    def append(self, piece: str, separator: str = "") -> None:
        addition = len(separator) + len(piece) if self._parts else len(piece)
        if self._total + addition > self._max_chars:
            raise ExtractedTextTooLargeError(self._max_chars)
        if separator and self._parts:
            self._parts.append(separator)
        self._parts.append(piece)
        self._total += addition

    def build(self) -> str:
        return "".join(self._parts)


class PdfExtractor:
    """Text-based PDFs via pypdf (maintained, pure-Python, no JS execution —
    embedded actions are inert data to it). Pages join with blank lines (a
    page break is a paragraph-scale boundary)."""

    file_type: FileType = "pdf"

    def extract(self, path: Path, *, max_chars: int) -> ExtractedDocument:
        from pypdf import PdfReader

        try:
            reader = PdfReader(str(path))
            page_count = len(reader.pages)
            if page_count > PDF_MAX_PAGES:
                raise FileTooLargeError(PDF_MAX_PAGES, reason="pdf_pages")
            budget = _CharBudget(max_chars)
            for page in reader.pages:
                budget.append(_clean_text(page.extract_text() or ""), separator="\n\n")
        except (ExtractedTextTooLargeError, FileTooLargeError):
            raise
        except Exception as exc:
            # pypdf error taxonomy (PdfReadError/PdfStreamError/…) is an
            # implementation detail — callers get the contract code; the log
            # keeps the type name only (messages can echo file bytes).
            raise ExtractionFailedError() from exc
        text = budget.build()
        if not text.strip():
            raise NoExtractableTextError()
        return ExtractedDocument(text=text, file_type="pdf", pages=page_count)


class DocxExtractor:
    """OOXML body text via python-docx, in TRUE document order (body XML
    iteration — `paragraphs`/`tables` are separate collections that would
    scramble interleaved content). Headings are plain paragraphs (their text
    is what segmentation needs); table rows join cells with ` | `; macros and
    embedded objects are never opened, let alone executed."""

    file_type: FileType = "docx"

    def extract(self, path: Path, *, max_chars: int) -> ExtractedDocument:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        try:
            document = Document(str(path))
            budget = _CharBudget(max_chars)
            for child in document.element.body.iterchildren():
                if child.tag == qn("w:p"):
                    budget.append(_clean_text(Paragraph(child, document).text), separator="\n")
                elif child.tag == qn("w:tbl"):
                    for row in Table(child, document).rows:
                        cells = [_clean_text(cell.text) for cell in row.cells]
                        if any(cells):
                            budget.append(" | ".join(cells), separator="\n")
        except ExtractedTextTooLargeError:
            raise
        except Exception as exc:
            raise ExtractionFailedError() from exc
        text = budget.build()
        if not text.strip():
            raise NoExtractableTextError()
        return ExtractedDocument(text=text, file_type="docx")


class TxtExtractor:
    """Plain text: deterministic decode chain (utf-8-sig → windows-1252 →
    latin-1 — the last cannot fail, so decode errors are impossible by
    construction, and NO bytes are ever discarded). Binary content was already
    rejected at validation (NUL sniff); anything arriving here is text."""

    file_type: FileType = "txt"

    def extract(self, path: Path, *, max_chars: int) -> ExtractedDocument:
        raw = path.read_bytes()
        text: str | None = None
        encoding: str | None = None
        for candidate in ("utf-8-sig", "windows-1252", "latin-1"):
            try:
                text = raw.decode(candidate)
            except UnicodeDecodeError:
                continue
            encoding = candidate
            break
        assert text is not None and encoding is not None  # latin-1 is total
        cleaned = _clean_text(text)
        if len(cleaned) > max_chars:
            raise ExtractedTextTooLargeError(max_chars)
        if not cleaned.strip():
            raise NoExtractableTextError()
        return ExtractedDocument(text=cleaned, file_type="txt", encoding=encoding)


EXTRACTORS: dict[FileType, DocumentExtractor] = {
    "pdf": PdfExtractor(),
    "docx": DocxExtractor(),
    "txt": TxtExtractor(),
}


def extract_text(path: Path, *, file_type: FileType, max_chars: int) -> ExtractedDocument:
    """Extract validated `path` with the type-correct reader (raises 4xx/422 —
    never returns partial text)."""
    return EXTRACTORS[file_type].extract(path, max_chars=max_chars)
