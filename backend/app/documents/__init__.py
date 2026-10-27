"""Secure document ingestion (Stage 08): validation + bounded extraction.

Pure of HTTP and the database: `validation` proves a staged file is what it
claims (4xx on any doubt); `extraction` reads verified files into pipeline
text (422 when unreadable/empty). Orchestration (streaming, storage,
transactions, analysis reuse) lives in `services/documents.py`.
"""

from app.documents.extraction import ExtractedDocument, extract_text
from app.documents.validation import FileType, ValidatedUpload, validate_staged_file

__all__ = [
    "ExtractedDocument",
    "FileType",
    "ValidatedUpload",
    "extract_text",
    "validate_staged_file",
]
