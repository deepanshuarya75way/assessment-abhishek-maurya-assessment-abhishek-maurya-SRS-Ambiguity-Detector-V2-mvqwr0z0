"""Application factory + process-level wiring.

Owns: settings, logging, middleware (request-id, security headers, access log,
CORS), lifespan (engine disposal), the uniform error envelope
(``the project contract`` §2), and router mounting. Feature code lives in
``app/api/``, ``app/services/``, etc. — never here.
"""

import re
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging, get_logger
from app.core.monitoring import capture_exception, init_monitoring
from app.email import get_email_service
from app.exceptions import AppError, RateLimitedError
from app.schemas.system import LiveResponse
from app.services.documents import shutdown_document_processing_executor

logger = get_logger(__name__)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "unprocessable_file",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


def error_envelope(code: str, message: str, details: object = None) -> dict[str, object]:
    """Build the uniform error body from ``the project contract`` §2."""
    return {"error": {"code": code, "message": message, "details": details}}


def _request_id_from_header(value: str | None) -> str:
    """Accept bounded caller ids for upstream correlation; generate otherwise."""
    if value is not None and _REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex[:12]


def _error_headers(request: Request, headers: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(headers or {})
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        merged["X-Request-ID"] = request_id
    return merged


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup needs no I/O by design; shutdown disposes the pooled engine."""
    _ = app
    yield
    shutdown_document_processing_executor()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    init_monitoring(settings)

    docs_kwargs: dict[str, str | None] = (
        {"docs_url": "/api/docs", "redoc_url": "/api/redoc", "openapi_url": "/api/openapi.json"}
        if not settings.is_production
        else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    )

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        debug=settings.DEBUG and not settings.is_production,
        lifespan=lifespan,
        **docs_kwargs,  # type: ignore[arg-type]
    )

    # Transactional email adapter (Resend prod / console dev). Fail-fast:
    # production misconfiguration crashes the boot, never the first register.
    app.state.email_service = get_email_service()

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _request_id_from_header(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
            # Framing denial (SECURITY_SPEC §8): JSON APIs are not frameable
            # content, but the headers close embedding of error pages and file
            # downloads. Prod-only so sandboxed/preview iframes keep working.
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    @app.middleware("http")
    async def access_log_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        # Path only (never query params) + status + latency; correlation via request_id.
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        request_id = getattr(request.state, "request_id", "-")
        logger.info(
            "%s %s -> %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "http_path": request.url.path,
                "http_route": route_path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, "internal_error")
        message = str(exc.detail) if exc.status_code < 500 else "Internal server error."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code, message),
            headers=_error_headers(request),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Contract: schema failures are 400 + "validation_error" (422 is reserved for
        # semantically-unprocessable FILES, e.g. extraction failures). Details are
        # field-level locators only — never echo secrets (Pydantic already masks SecretStr).
        details = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg", "invalid")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_envelope("validation_error", "Request validation failed.", details),
            headers=_error_headers(request),
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        if exc.status_code >= 500:
            logger.error(
                "Application error",
                extra={
                    "request_id": request_id,
                    "error_code": exc.code,
                    "exception_class": type(exc).__name__,
                },
            )
            capture_exception(
                exc,
                request_id=request_id,
                context={"error_code": exc.code, "exception_class": type(exc).__name__},
            )
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if isinstance(exc, RateLimitedError)
            else None
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, exc.details),
            headers=_error_headers(request, headers),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Sanitized: driver errors may carry SQL/DSN fragments — log server-side only.
        _ = exc
        request_id = getattr(request.state, "request_id", "-")
        logger.exception(
            "Database error",
            extra={
                "request_id": request_id,
                "error_code": "internal_error",
                "database_operation": "request",
            },
        )
        capture_exception(
            exc,
            request_id=request_id,
            context={"error_code": "internal_error", "database_operation": "request"},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope("internal_error", "Internal server error."),
            headers=_error_headers(request),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.exception(
            "Unhandled exception",
            extra={
                "request_id": request_id,
                "error_code": "internal_error",
                "exception_class": type(exc).__name__,
            },
        )
        capture_exception(
            exc,
            request_id=request_id,
            context={"error_code": "internal_error", "exception_class": type(exc).__name__},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope("internal_error", "Internal server error."),
            headers=_error_headers(request),
        )

    @app.get("/health", include_in_schema=False)
    async def health_alias() -> LiveResponse:
        """Stable infrastructure probe (load balancers, uptime checks, PaaS).

        The canonical contract lives at /api/v1/health/* (API_CONTRACT.md §4.1).
        This unversioned alias exists ONLY so infrastructure has a fixed path that
        never moves across API versions. It returns the live payload, nothing more —
        no env details, no dependency internals (SECURITY_SPEC §2).
        """
        return LiveResponse()

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": "srs-ambiguity-detector",
            "version": __version__,
            "docs": "/api/docs",
        }

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
