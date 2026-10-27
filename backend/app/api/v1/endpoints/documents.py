"""Document endpoints (API_CONTRACT §4.4 — Stage 08: upload+analyze, metadata read;
Stage 19: list, purge-by-id, signed-URL downloads).

Thin: guards (verified identity + CSRF + per-user buckets on mutations,
identity-only on the safe GETs) → service → response. `POST /upload` analyzes
EXACTLY one file per call (sync pipeline — bounded request, honest 503 past
the processing budget); extra `file` parts are rejected, never silently
dropped. Reads are owner-scoped: foreign ids 404 exactly like missing ones.
The streaming download GET carries no session — its short-lived,
single-document token IS the credential (the access log records paths only,
never query strings, so the bearer never lands in logs).
"""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_verified_user, verified_user_guard
from app.api.v1.presenters import detail_response
from app.core.config import get_settings
from app.core.database import get_session
from app.core.rate_limit import check_rate_limit
from app.core.security import decode_document_download_token
from app.exceptions import TooManyFilesError
from app.schemas.analysis import TITLE_MAX_LENGTH
from app.schemas.common import Page, PaginationParams
from app.schemas.documents import (
    DocumentDownloadUrlResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.services import documents as documents_service
from app.services.auth import UserInfo
from app.services.documents import DocumentDetail

router = APIRouter(prefix="/documents", tags=["documents"])

# Uploads are resource-intensive: tighter per-user budget than text posts.
upload_guard = verified_user_guard(
    "documents:upload", limit=lambda: get_settings().RATE_LIMIT_UPLOADS_PER_MINUTE
)
delete_guard = verified_user_guard("documents:delete")
# Minting issues a bearer credential: dedicated tight bucket (the streaming
# GET rides the default bucket keyed by the token's owner instead).
download_url_guard = verified_user_guard(
    "documents:download-url",
    limit=lambda: get_settings().RATE_LIMIT_DOCUMENT_DOWNLOAD_PER_MINUTE,
)


def _document_response(item: DocumentDetail) -> DocumentResponse:
    # Metadata only — storage key / binary / extracted text never serialize.
    if item.file_type not in ("pdf", "docx", "txt"):
        raise ValueError(f"unexpected file type: {item.file_type!r}")
    if item.extraction_status not in ("pending", "ok", "failed"):
        raise ValueError(f"unexpected extraction status: {item.extraction_status!r}")
    return DocumentResponse(
        id=item.id,
        filename=item.filename,
        file_type=item.file_type,  # type: ignore[arg-type]  # narrowed above
        mime_type=item.mime_type,
        byte_size=item.byte_size,
        sha256=item.sha256,
        extracted_chars=item.extracted_chars,
        extraction_status=item.extraction_status,  # type: ignore[arg-type]  # ditto
        created_at=item.created_at,
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    files: Annotated[list[UploadFile], File(...)],
    user: Annotated[UserInfo, Depends(upload_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
    title: Annotated[str | None, Form(max_length=TITLE_MAX_LENGTH)] = None,
    ai_enhance: Annotated[bool, Form()] = False,
) -> DocumentUploadResponse:
    """Upload one SRS file (pdf/docx/txt) → validate → extract → run the SAME
    deterministic pipeline as pasted text → 201 `{document, analysis}`.
    `ai_enhance` (Stage 14) opts the shared post-commit AI step in."""
    max_files = get_settings().MAX_FILES_PER_REQUEST
    if len(files) > max_files:
        raise TooManyFilesError(max_files)
    if not files:  # unreachable: File(...) required → 400 validation_error
        raise TooManyFilesError(max_files)  # pragma: no cover - defensive
    # NOTE: exactly one file is processed (files[0]). If MAX_FILES_PER_REQUEST
    # is ever raised, this endpoint must grow real multi-file support — the
    # `> max_files` gate above is what keeps extra parts from silent dropping.
    upload = files[0]
    try:
        document, analysis = await documents_service.upload_and_analyze(
            session,
            owner_id=user.id,
            filename=upload.filename,
            content_type=upload.content_type,
            read=upload.read,
            title=title,
            ai_enhance=ai_enhance,
        )
    finally:
        await upload.close()  # releases the multipart spool file, always
    return DocumentUploadResponse(
        document=_document_response(document), analysis=detail_response(analysis)
    )


@router.get("", response_model=Page[DocumentResponse])
async def list_documents(
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    paging: Annotated[PaginationParams, Depends()],
) -> Page[DocumentResponse]:
    """Newest-first page of owned documents (contract §3 envelope)."""
    items, total = await documents_service.list_documents(
        session,
        owner_id=user.id,
        page=paging.page,
        page_size=paging.page_size,
    )
    return Page[DocumentResponse](
        items=[_document_response(item) for item in items],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user: Annotated[UserInfo, Depends(get_current_verified_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    """One owned document's metadata (binary/downloads arrive later — §4.4)."""
    detail = await documents_service.get_document_detail(
        session, owner_id=user.id, document_id=document_id
    )
    return _document_response(detail)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    user: Annotated[UserInfo, Depends(delete_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Purge one owned document (row + stored binary → 204 | 404).

    Referencing analyses survive (their `document` pointer degrades to
    null — results never needed the binary)."""
    await documents_service.delete_document(session, owner_id=user.id, document_id=document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/download-url", response_model=DocumentDownloadUrlResponse)
async def mint_download_url(
    document_id: UUID,
    user: Annotated[UserInfo, Depends(download_url_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentDownloadUrlResponse:
    """Mint a short-lived signed download URL (200 | 404 unless owned).

    The URL is origin-relative (prefix included — resolve against the API
    origin) and single-document; it expires after DOCUMENT_DOWNLOAD_URL_MINUTES.
    The token must never be logged or stored — treat the URL as a bearer
    credential until it expires."""
    url, expires_at = await documents_service.mint_download_url(
        session, owner_id=user.id, document_id=document_id
    )
    return DocumentDownloadUrlResponse(download_url=url, expires_at=expires_at)


def _content_disposition(filename: str) -> str:
    """`attachment` disposition naming the sanitized filename.

    Both the legacy `filename` param (ASCII fallback — the sanitizer keeps
    unicode but strips controls) and RFC 5987 `filename*` (widest client
    support); never `inline` (SECURITY_SPEC §5: stored uploads are never
    rendered as HTML).
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    ascii_name = ascii_name.replace("\\", "_").replace('"', "_")
    if not ascii_name.strip("._"):
        ascii_name = "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    token: Annotated[str, Query(max_length=2048)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Stream one owned document's original bytes (200 | 400 | 404).

    No session: the `token` query bearer (minted above) IS the credential —
    expired/forged/mismatched tokens fail 400 `invalid_token`, a document
    deleted after minting fails 404. Bytes are integrity-checked before
    release; served as `attachment` under the server-detected MIME.
    """
    owner_id = decode_document_download_token(token, document_id)
    check_rate_limit(f"documents:download:owner:{owner_id}")
    payload = await documents_service.read_document_bytes(
        session, owner_id=owner_id, document_id=document_id
    )
    return Response(
        content=payload.data,
        media_type=payload.mime_type,
        headers={"content-disposition": _content_disposition(payload.filename)},
    )
