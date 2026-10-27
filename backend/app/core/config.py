"""Centralized, env-driven settings (ADR: no stray ``os.getenv`` in feature code).

Every setting is validated at boot. See ``backend/.env.example`` for the full matrix
and ``the project contract`` §7 for the stage-by-stage breakdown.
"""

from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Instantiate via :func:`get_settings` (cached)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "SRS Ambiguity Detector"
    APP_ENV: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # Exact origins, e.g. "https://app.example.com,https://www.example.com".
    # Accepts a JSON list OR a comma-separated string.
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Stage 02+: DATABASE_URL drives the app; DIRECT_DATABASE_URL (optional, falls
    # back to DATABASE_URL) drives Alembic — on Supabase it bypasses the pooler,
    # which cannot run DDL in transaction-pooling mode.
    DATABASE_URL: str | None = None
    DIRECT_DATABASE_URL: str | None = None
    # Stage 25: deployment-tunable asyncpg pool. Defaults are intentionally
    # conservative; operators should size per process against database capacity.
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT_SECONDS: int = 30
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800

    # --- Stage 04: authentication ---
    # JWT_SECRET signs access tokens (HS256, 256-bit minimum). REQUIRED for any
    # auth endpoint — fail closed (RuntimeError on first use, never a default).
    JWT_SECRET: str | None = None
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 30
    PASSWORD_RESET_MINUTES: int = 60
    # resend | console. console = dev-only (metadata logs + full mail to
    # DEV_OUTBOX_DIR, refused in production); resend = Resend HTTP API.
    EMAIL_PROVIDER: Literal["resend", "console"] = "console"
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "SRS Ambiguity Detector <noreply@example.com>"
    # Public base URL used to build password-reset links.
    APP_BASE_URL: str = "http://localhost:3000"
    DEV_OUTBOX_DIR: str = "./.dev-outbox"
    # Auth rate limits (single-process token buckets; Stage 22 distributes).
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MINUTE: int = 60
    # --- Stage 06: analysis creation budget (per verified user per minute) ---
    RATE_LIMIT_ANALYSIS_PER_MINUTE: int = 20
    # --- Stage 08: secure document upload + extraction (SECURITY_SPEC §5) ---
    # Uploads are resource-intensive: tighter per-user budget than text posts.
    RATE_LIMIT_UPLOADS_PER_MINUTE: int = 10
    # Per-file byte cap (streaming-enforced; the true byte count, never the
    # client-declared size). 10 MiB holds very large SRS documents.
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    # Extracted-text char cap. Equals the TEXT pipeline budget (TEXT_MAX_LENGTH)
    # so extracted text flows into the SAME segmentation/engine path unmodified.
    MAX_EXTRACTED_TEXT_CHARS: int = 200_000
    # Files per upload request. 1: the sync pipeline analyzes one file per call
    # (bounded request; the endpoint signature enforces this structurally).
    MAX_FILES_PER_REQUEST: int = 1
    # Wall-clock budget for validate+extract (worker thread; the request fails
    # 503 past this — the temp file is still always cleaned up).
    DOCUMENT_PROCESSING_TIMEOUT_SECONDS: int = 60
    # Maximum simultaneous validate+extract workers per backend process. This
    # bounds timed-out parser work that CPython cannot kill mid-call.
    DOCUMENT_EXTRACTOR_WORKERS: int = 2
    # Storage backend: local dev/single-instance disk or Supabase Storage for managed production.
    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    STORAGE_LOCAL_DIR: str = "./uploads"
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_STORAGE_BUCKET: str | None = None
    # --- Stage 19: signed document downloads (SECURITY_SPEC §5) ---
    # Signed-URL lifetime (minutes). SECURITY_SPEC §5 caps this at 15 —
    # the validator below refuses anything higher at boot.
    DOCUMENT_DOWNLOAD_URL_MINUTES: int = 15
    # Per-user download-URL mints per minute (minting issues a bearer
    # credential — tighter than the auth default; the streaming GET rides
    # the default bucket keyed by the token's owner).
    RATE_LIMIT_DOCUMENT_DOWNLOAD_PER_MINUTE: int = 10
    # argon2id work factors. Tests override via env (fast-but-real params).
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536
    ARGON2_PARALLELISM: int = 4
    # --- Stage 12: AI credential vault (SECURITY_SPEC §4) ---
    # Fernet master key (32 bytes, base64) for per-user provider keys at rest.
    # Absent by default (AI is optional — the app boots and analyzes without
    # it); REQUIRED for any vault write/read — fail closed on first use.
    # There are deliberately NO global GEMINI/GROQ/OPENAI/... keys, ever.
    ENCRYPTION_MASTER_KEY: str | None = None
    # Credential-test budget: per-user tests per minute (tests can trigger
    # external provider calls — tighter than the auth default).
    RATE_LIMIT_AI_TEST_PER_MINUTE: int = 10
    # Explicit retry budget: retry-ai can trigger the same provider work as a
    # fresh enhanced run, so it gets its own AI bucket (Stage 21 as-built).
    RATE_LIMIT_AI_RETRY_PER_MINUTE: int = 10
    # --- Stage 24: monitoring / Sentry (optional; never required for local dev) ---
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None
    SENTRY_RELEASE: str | None = None
    # Tracing is disabled by default; operators can enable a low sample rate.
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    # --- Stage 14: AI enhancement budgets (AI_PROVIDER_SPEC §2) ---
    # Per-call provider timeout (seconds); adapters clamp every `timeout_s`
    # into [1, AI_MAX_TIMEOUT_S]. DEFAULT > MAX is operator misconfig and
    # fails boot loudly (the model validator below) rather than silently.
    AI_DEFAULT_TIMEOUT_S: int = 25
    AI_MAX_TIMEOUT_S: int = 60

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return value  # let pydantic-settings parse JSON
            return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
        return value

    @field_validator("JWT_SECRET")
    @classmethod
    def _jwt_secret_strength(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes (256 bits).")
        return value

    @field_validator("ENCRYPTION_MASTER_KEY")
    @classmethod
    def _master_key_wellformed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            Fernet(value.encode("utf-8"))
        except ValueError:
            # Never echo the value: the message names the variable only.
            raise ValueError(
                "ENCRYPTION_MASTER_KEY must be a Fernet key (32 bytes, base64). "
                "Generate one per backend/.env.example."
            ) from None
        return value

    @model_validator(mode="after")
    def _database_pool_budget_valid(self) -> "Settings":
        if self.DATABASE_POOL_SIZE < 1:
            raise ValueError("DATABASE_POOL_SIZE must be at least 1.")
        if self.DATABASE_MAX_OVERFLOW < 0:
            raise ValueError("DATABASE_MAX_OVERFLOW must be non-negative.")
        if self.DATABASE_POOL_TIMEOUT_SECONDS < 1:
            raise ValueError("DATABASE_POOL_TIMEOUT_SECONDS must be at least 1.")
        if self.DATABASE_POOL_RECYCLE_SECONDS < 60:
            raise ValueError("DATABASE_POOL_RECYCLE_SECONDS must be at least 60.")
        return self

    @model_validator(mode="after")
    def _ai_timeout_budget_coherent(self) -> "Settings":
        if self.AI_MAX_TIMEOUT_S < 1:
            raise ValueError("AI_MAX_TIMEOUT_S must be at least 1.")
        if not 1 <= self.AI_DEFAULT_TIMEOUT_S <= self.AI_MAX_TIMEOUT_S:
            raise ValueError("AI_DEFAULT_TIMEOUT_S must be within [1, AI_MAX_TIMEOUT_S].")
        return self

    @model_validator(mode="after")
    def _document_extractor_workers_valid(self) -> "Settings":
        if not 1 <= self.DOCUMENT_EXTRACTOR_WORKERS <= 8:
            raise ValueError("DOCUMENT_EXTRACTOR_WORKERS must be within [1, 8].")
        return self

    @model_validator(mode="after")
    def _download_ttl_within_spec_cap(self) -> "Settings":
        # SECURITY_SPEC §5 caps signed-URL life at 15 min — an operator
        # override above that fails boot loudly rather than silently.
        if not 1 <= self.DOCUMENT_DOWNLOAD_URL_MINUTES <= 15:
            raise ValueError("DOCUMENT_DOWNLOAD_URL_MINUTES must be within [1, 15].")
        return self

    @model_validator(mode="after")
    def _supabase_storage_configured(self) -> "Settings":
        if self.STORAGE_BACKEND != "supabase":
            return self
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self.SUPABASE_URL),
                ("SUPABASE_SERVICE_ROLE_KEY", self.SUPABASE_SERVICE_ROLE_KEY),
                ("SUPABASE_STORAGE_BUCKET", self.SUPABASE_STORAGE_BUCKET),
            )
            if not value
        ]
        if missing:
            raise ValueError("STORAGE_BACKEND=supabase requires " + ", ".join(missing) + ".")
        return self

    @model_validator(mode="after")
    def _sentry_sampling_valid(self) -> "Settings":
        if not 0 <= self.SENTRY_TRACES_SAMPLE_RATE <= 1:
            raise ValueError("SENTRY_TRACES_SAMPLE_RATE must be within [0, 1].")
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
