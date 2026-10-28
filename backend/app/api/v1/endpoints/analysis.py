
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_current_verified_user,
    verified_user_guard,
)
from app.api.v1.presenters import (
    requirement_response,
    detail_response,
    retry_ai_response,
    summary_response,
)
from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.analysis import (
    RequirementResponse,
    AnalysisCreateRequest,
    AnalysisDetailResponse,
    AnalysisSummaryResponse,
    RetryAiResponse,
)
from app.schemas.common import Page, PaginationParams
from app.services import analysis as analysis_service
from app.services.auth import UserInfo


router = APIRouter(prefix="/analysis", tags=["analysis"])


# Guards
create_guard = verified_user_guard(
    "analysis:create",
    limit=lambda: get_settings().RATE_LIMIT_ANALYSIS_PER_MINUTE,
)

delete_guard = verified_user_guard("analysis:delete")

retry_guard = verified_user_guard(
    "analysis:retry-ai",
    limit=lambda: get_settings().RATE_LIMIT_AI_RETRY_PER_MINUTE,
)


# Query parameter types
SortParam = Literal[
    "created_at",
    "-created_at",
    "score",
    "-score",
]

BandParam = Literal[
    "low",
    "moderate",
    "high",
    "very_high",
]

SourceTypeParam = Literal["text", "document"]


@router.post(
    "",
    response_model=AnalysisDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_analysis(
    body: AnalysisCreateRequest,
    user: Annotated[UserInfo, Depends(create_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalysisDetailResponse:
    detail = await analysis_service.create_text_analysis(
        session,
        owner_id=user.id,
        title=body.title,
        text=body.text,
        document_id=body.document_id,
        ai_enhance=body.options.ai_enhance,
    )

    return detail_response(detail)


@router.get(
    "",
    response_model=Page[AnalysisSummaryResponse],
)
async def list_analyses(
    user: Annotated[
        UserInfo, Depends(get_current_verified_user)
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    paging: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParam, Query()] = "-created_at",
    band: Annotated[BandParam | None, Query()] = None,
    source_type: Annotated[SourceTypeParam | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[AnalysisSummaryResponse]:
    """List the current user's analyses with filtering and pagination."""

    items, total = await analysis_service.list_analyses(
        session,
        owner_id=user.id,
        page=paging.page,
        page_size=paging.page_size,
        sort=sort,
        band=band,
        source_type=source_type,
        q=q,
    )

    return Page[AnalysisSummaryResponse](
        items=[summary_response(item) for item in items],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )


@router.get(
    "/{analysis_id}/requirements",
    response_model=Page[RequirementResponse],
)
async def list_requirements(
    analysis_id: UUID,
    user: Annotated[
        UserInfo, Depends(get_current_verified_user)
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    paging: Annotated[PaginationParams, Depends()],
    q: str = Query("", max_length=200),
    status_filter: Literal[
        "all", "with-issues", "clean"
    ] = Query("all", alias="status"),
    severity: Literal[
        "all", "low", "medium", "high", "critical"
    ] = Query("all"),
    sort: Literal[
        "original", "lowest-score", "most-issues"
    ] = Query("original"),
) -> Page[RequirementResponse]:
    """List, search, filter, sort, and paginate analysis requirements."""

    detail = await analysis_service.get_analysis_detail(
        session,
        owner_id=user.id,
        analysis_id=analysis_id,
    )

    rows = list(detail.requirements)

    # Search requirement text and identifier.
    if q.strip():
        search_text = q.strip().lower()

        rows = [
            requirement
            for requirement in rows
            if search_text in requirement.text.lower()
            or search_text
            in (requirement.identifier or "").lower()
        ]

    # Filter by issue status.
    if status_filter == "with-issues":
        rows = [
            requirement
            for requirement in rows
            if requirement.issues_count > 0
        ]
    elif status_filter == "clean":
        rows = [
            requirement
            for requirement in rows
            if requirement.issues_count == 0
        ]

    # Filter by severity.
    if severity != "all":
        rows = [
            requirement
            for requirement in rows
            if requirement.severity == severity
        ]

    # Sort the requirements.
    if sort == "lowest-score":
        rows.sort(
            key=lambda requirement: (
                requirement.score is None,
                (
                    requirement.score
                    if requirement.score is not None
                    else 0
                ),
            )
        )

    elif sort == "most-issues":
        rows.sort(
            key=lambda requirement: requirement.issues_count,
            reverse=True,
        )

    # Calculate the total before pagination.
    total = len(rows)

    # Apply pagination.
    offset = (paging.page - 1) * paging.page_size

    rows = rows[
        offset : offset + paging.page_size
    ]

    return Page[RequirementResponse](
        items=[
            requirement_response(requirement)
            for requirement in rows
        ],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )


@router.get(
    "/{analysis_id}",
    response_model=AnalysisDetailResponse,
)
async def get_analysis(
    analysis_id: UUID,
    user: Annotated[
        UserInfo, Depends(get_current_verified_user)
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalysisDetailResponse:
    detail = await analysis_service.get_analysis_detail(
        session,
        owner_id=user.id,
        analysis_id=analysis_id,
    )

    return detail_response(detail)


@router.delete(
    "/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_analysis(
    analysis_id: UUID,
    user: Annotated[UserInfo, Depends(delete_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await analysis_service.delete_analysis(
        session,
        owner_id=user.id,
        analysis_id=analysis_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{analysis_id}/retry-ai",
    response_model=RetryAiResponse,
)
async def retry_ai(
    analysis_id: UUID,
    user: Annotated[UserInfo, Depends(retry_guard)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RetryAiResponse:
    """Retry only the AI enhancement step for an existing analysis."""

    detail = await analysis_service.retry_analysis_ai(
        session,
        owner_id=user.id,
        analysis_id=analysis_id,
    )

    return retry_ai_response(detail)
