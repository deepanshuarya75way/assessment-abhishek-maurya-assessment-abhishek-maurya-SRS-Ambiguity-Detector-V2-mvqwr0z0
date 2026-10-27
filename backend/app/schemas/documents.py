"""Document API boundary models (API_CONTRACT §4.4 — Stage 08 subset).

Upload is multipart (no JSON body schema — the endpoint declares `files` +
`title` form fields); these cover RESPONSES only. Metadata-only, always: the
storage key, the binary, and the extracted text are never serialized (the
analysis nests the requirements + findings instead).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.analysis import AnalysisDetailResponse

DocumentFileType = Literal["pdf", "docx", "txt"]
ExtractionStatus = Literal["pending", "ok", "failed"]


class DocumentResponse(BaseModel):
    """One uploaded document's metadata (contract §4.4 `Document`)."""

    id: uuid.UUID
    filename: str
    file_type: DocumentFileType
    mime_type: str
    byte_size: int
    sha256: str
    extracted_chars: int
    extraction_status: ExtractionStatus
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    """POST /documents/upload result: the stored document + its full
    deterministic analysis (contract §4.4 — one file per call, analyzed
    synchronously, same detail shape as POST /analysis)."""

    document: DocumentResponse
    analysis: AnalysisDetailResponse


class DocumentDownloadUrlResponse(BaseModel):
    """POST /documents/{id}/download-url result (contract §4.4, Stage 19).

    `download_url` is an origin-RELATIVE path (`{prefix}/documents/{id}/
    download?token=…`, prefix included) — clients resolve it against the
    API origin. The token is single-document, short-lived, and must never
    be logged.
    """

    download_url: str
    expires_at: datetime
