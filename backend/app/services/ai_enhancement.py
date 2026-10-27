"""Optional AI enhancement of a persisted analysis (Stage 14; API_CONTRACT §4.3).

Runs AFTER the deterministic pipeline commits: validate → normalize →
segment → detect → score → PERSIST → AI → persist AI → return. No
transaction ever spans the provider network I/O — the deterministic result
commits first (caller's boundary), provider calls run bare, and outcomes
land in ONE short follow-up transaction (`_persist_outcome`).

Fail-open is absolute: provider errors, vault outages, and even our own
bugs in the AI path NEVER fail the analysis — the deterministic detail
persists and returns with an honest `ai_status` + user-safe `ai_error`.

Status mapping (the `ck_analyses_ai_status` vocabulary is binding):
- `ai_enhance=false` → `skipped` (no credential read, no UPDATE — the row
  default already says `skipped`).
- no ENABLED credential → `unconfigured` (`ai_error` NULL — not an error,
  the UI renders its empty state + Settings CTA).
- enabled credentials but NO adapter (defensive — all six ship adapters
  since Stage 18, so only a not-yet-wired future provider lands here) →
  `failed` + "<Label> integration isn't available yet." (a key IS stored,
  so `unconfigured` would lie).
- overview succeeds → `ok` (+ best-effort per-requirement rewrites, same
  provider — attribution never mixes providers within a run).
- every attempt fails → `failed` + the FIRST provider's message (chain
  order is default-first, so the first error is the most actionable one).

Chain: default → fallbacks in rank order (AI_PROVIDER_SPEC §5/§7), max 3
attempts; failover triggers ONLY on overview failure (a cursed rewrite
must not burn the chain). Improvements run on the WINNING provider only,
for requirements WITH issues, capped per run, under bounded concurrency
(spec §9: no auto-fan-out across 500 requirements).

Secrets discipline: ciphertext decrypts per attempt, plaintext lives in a
local handed to the adapter in-process, and is never persisted, logged,
or returned. Logs carry provider ids + error codes + latency only.
"""

import asyncio
import uuid
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers import (
    AIProvider,
    FindingSummary,
    ImprovementPayload,
    OverviewPayload,
    ProviderError,
)
from app.ai.registry import PROVIDER_METADATA, resolve_adapter
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.monitoring import capture_message
from app.core.vault import VaultError, decrypt_secret
from app.repositories.ai_providers import AICredentialRepository
from app.repositories.analysis import AnalysisRepository, RequirementRepository
from app.services.analysis import AnalysisDetail, IssueDetail, RequirementDetail
from app.services.transactions import transactional

logger = get_logger(__name__)

# Spec §7: max chain = 3 attempts (default + up to 2 fallbacks).
_MAX_CHAIN_ATTEMPTS = 3
# Spec §9: no auto-fan-out — at most 10 rewrites per run (lowest positions
# first among requirements WITH issues; the rest keep deterministic-only).
_MAX_IMPROVEMENTS_PER_RUN = 10
# Bounded concurrency for the improvement wave (the overview always runs solo).
_MAX_AI_CONCURRENCY = 4
# Mirrors analyses.ai_error VARCHAR(300).
_AI_ERROR_MAX_LENGTH = 300

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_UNEXPECTED_MESSAGE = "AI enhancement failed unexpectedly."
_VAULT_MESSAGE = "AI enhancement is temporarily unavailable."


async def enhance_analysis(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    detail: AnalysisDetail,
    ai_enhance: bool,
) -> AnalysisDetail:
    """Run the optional AI step for a JUST-PERSISTED analysis detail.

    Pure orchestration around `detail` (frozen — every outcome builds a new
    one via `replace`): resolves the credential chain, calls providers
    through the ABC (no provider-specific branches — the adapter carries
    the shape), persists the outcome, and returns the detail the endpoint
    serializes. TEXT and DOCUMENT callers share this (same pipeline, same
    vocabulary).
    """
    if not ai_enhance:
        return detail  # `skipped` + NULLs are the row/detail defaults
    chain = await AICredentialRepository(session).list_enabled_chain(owner_id=owner_id)
    if not chain:
        await _persist_outcome(
            session,
            owner_id=owner_id,
            analysis_id=detail.id,
            ai_overview=None,
            ai_provider=None,
            ai_status="unconfigured",
            ai_error=None,
            rewrites={},
        )
        return replace(detail, ai_status="unconfigured")
    usable: list[tuple[uuid.UUID, str, AIProvider]] = []
    for row in chain:
        adapter = resolve_adapter(row.provider)
        if adapter is not None:
            usable.append((row.id, row.provider, adapter))
        if len(usable) >= _MAX_CHAIN_ATTEMPTS:
            break
    if not usable:
        # Credentials exist but none resolves an adapter (defensive: all six
        # ship adapters since Stage 18) — name the FIRST chain entry (the
        # default when one is set): one concrete label beats a vague plural.
        label = PROVIDER_METADATA[chain[0].provider].display_name
        message = f"{label} integration isn't available yet."
        await _persist_outcome(
            session,
            owner_id=owner_id,
            analysis_id=detail.id,
            ai_overview=None,
            ai_provider=None,
            ai_status="failed",
            ai_error=message,
            rewrites={},
        )
        return replace(detail, ai_status="failed", ai_error=message)

    timeout_s = get_settings().AI_DEFAULT_TIMEOUT_S
    overview_payload = _overview_payload(detail)
    attempted: list[str] = []
    first_message: str | None = None
    credentials = {row.id: row for row in chain}
    for credential_id, provider_id, adapter in usable:
        attempted.append(provider_id)
        try:
            api_key = decrypt_secret(credentials[credential_id].encrypted_api_key)
        except VaultError:
            # OUR outage (or a tampered row) — fail open with a generic
            # message; the vault's internals never reach the response.
            logger.error(
                "ai enhancement vault failure analysis_id=%s owner_id=%s provider=%s",
                detail.id,
                owner_id,
                provider_id,
                extra={
                    "analysis_stage": "ai_enhancement",
                    "ai_provider": provider_id,
                    "error_code": "vault_error",
                },
            )
            capture_message(
                "ai enhancement vault failure",
                level="error",
                context={
                    "analysis_stage": "ai_enhancement",
                    "ai_provider": provider_id,
                    "error_code": "vault_error",
                },
            )
            if first_message is None:
                first_message = _VAULT_MESSAGE
            continue
        try:
            overview = await adapter.generate_overview(
                api_key, overview_payload, timeout_s=timeout_s
            )
        except ProviderError as exc:
            logger.info(
                "ai enhancement provider failed analysis_id=%s owner_id=%s provider=%s code=%s",
                detail.id,
                owner_id,
                provider_id,
                exc.code,
                extra={
                    "analysis_stage": "ai_enhancement",
                    "ai_provider": provider_id,
                    "error_code": exc.code,
                },
            )
            capture_message(
                "ai enhancement provider failed",
                level="warning",
                context={
                    "analysis_stage": "ai_enhancement",
                    "ai_provider": provider_id,
                    "error_code": exc.code,
                },
            )
            if first_message is None:
                first_message = exc.user_message
            continue
        except Exception as exc:
            # Even adapter bugs fail OPEN (the deterministic result already
            # persisted): log the exception TYPE only — messages/tracebacks
            # could carry provider text that must never hit the log store.
            logger.error(
                "ai enhancement crashed analysis_id=%s owner_id=%s provider=%s exc=%s",
                detail.id,
                owner_id,
                provider_id,
                type(exc).__name__,
                extra={
                    "analysis_stage": "ai_enhancement",
                    "ai_provider": provider_id,
                    "exception_class": type(exc).__name__,
                },
            )
            capture_message(
                "ai enhancement crashed",
                level="error",
                context={
                    "analysis_stage": "ai_enhancement",
                    "ai_provider": provider_id,
                    "exception_class": type(exc).__name__,
                },
            )
            if first_message is None:
                first_message = _UNEXPECTED_MESSAGE
            continue
        rewrites = await _improve_requirements(
            adapter,
            api_key,
            detail,
            owner_id=owner_id,
            provider_id=provider_id,
            timeout_s=timeout_s,
        )
        await _persist_outcome(
            session,
            owner_id=owner_id,
            analysis_id=detail.id,
            ai_overview=overview.text,
            ai_provider=provider_id,
            ai_status="ok",
            ai_error=None,
            rewrites=rewrites,
        )
        logger.info(
            "ai enhancement ok analysis_id=%s owner_id=%s provider=%s model=%s "
            "improvements=%d latency_ms=%d",
            detail.id,
            owner_id,
            provider_id,
            overview.model,
            len(rewrites),
            overview.latency_ms,
            extra={
                "analysis_stage": "ai_enhancement",
                "ai_provider": provider_id,
                "ai_model": overview.model,
                "duration_ms": overview.latency_ms,
            },
        )
        return replace(
            detail,
            ai_overview=overview.text,
            ai_provider=provider_id,
            ai_status="ok",
            requirements=_apply_rewrites(detail.requirements, rewrites),
        )
    message = (first_message or _UNEXPECTED_MESSAGE)[:_AI_ERROR_MAX_LENGTH]
    await _persist_outcome(
        session,
        owner_id=owner_id,
        analysis_id=detail.id,
        ai_overview=None,
        ai_provider=None,
        ai_status="failed",
        ai_error=message,
        rewrites={},
    )
    logger.info(
        "ai enhancement failed analysis_id=%s owner_id=%s attempted=%s",
        detail.id,
        owner_id,
        ",".join(attempted),
        extra={"analysis_stage": "ai_enhancement", "error_code": "ai_unavailable"},
    )
    return replace(detail, ai_status="failed", ai_error=message)


async def _improve_requirements(
    adapter: AIProvider,
    api_key: str,
    detail: AnalysisDetail,
    *,
    owner_id: uuid.UUID,
    provider_id: str,
    timeout_s: int,
) -> dict[uuid.UUID, str]:
    """Best-effort rewrites on the WINNING provider (never triggers failover).

    Only requirements WITH issues qualify (clean ones need no rewrite);
    lowest positions first, capped per run. One cursed requirement can only
    cost itself — every failure maps to a skipped rewrite, never an error.
    """
    targets = [item for item in detail.requirements if item.issues][:_MAX_IMPROVEMENTS_PER_RUN]
    semaphore = asyncio.Semaphore(_MAX_AI_CONCURRENCY)

    async def _one(item: RequirementDetail) -> tuple[uuid.UUID, str] | None:
        async with semaphore:
            try:
                result = await adapter.generate_improvement(
                    api_key, _improvement_payload(item), timeout_s=timeout_s
                )
            except ProviderError as exc:
                logger.info(
                    "ai improvement skipped analysis_id=%s requirement_id=%s provider=%s code=%s",
                    detail.id,
                    item.id,
                    provider_id,
                    exc.code,
                    extra={
                        "analysis_stage": "ai_improvement",
                        "ai_provider": provider_id,
                        "error_code": exc.code,
                    },
                )
                return None
            except Exception as exc:
                logger.error(
                    "ai improvement crashed analysis_id=%s requirement_id=%s provider=%s exc=%s",
                    detail.id,
                    item.id,
                    provider_id,
                    type(exc).__name__,
                    extra={
                        "analysis_stage": "ai_improvement",
                        "ai_provider": provider_id,
                        "exception_class": type(exc).__name__,
                    },
                )
                capture_message(
                    "ai improvement crashed",
                    level="error",
                    context={
                        "analysis_stage": "ai_improvement",
                        "ai_provider": provider_id,
                        "exception_class": type(exc).__name__,
                    },
                )
                return None
            return (item.id, result.text)

    completed = await asyncio.gather(*(_one(item) for item in targets))
    return {item_id: text for found in completed if found is not None for item_id, text in [found]}


@transactional
async def _persist_outcome(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    analysis_id: uuid.UUID,
    ai_overview: str | None,
    ai_provider: str | None,
    ai_status: str,
    ai_error: str | None,
    rewrites: dict[uuid.UUID, str],
) -> None:
    """ONE short transaction for the AI outcome (network I/O is over by now).

    Touches ONLY `ai_*` columns + the improved requirements' rewrite fields —
    deterministic scores/findings are never rewritten here.
    """
    affected = await AnalysisRepository(session).record_ai_result(
        owner_id=owner_id,
        analysis_id=analysis_id,
        ai_overview=ai_overview,
        ai_provider=ai_provider,
        ai_status=ai_status,
        ai_error=ai_error,
    )
    if rewrites:
        await RequirementRepository(session).set_suggested_rewrites(
            analysis_id=analysis_id, rewrites=rewrites
        )
    if affected == 0:
        # The analysis was deleted mid-run (concurrent DELETE): the outcome
        # has no row to land on. Log (ids only) — the caller still returns
        # the in-memory detail honestly.
        logger.warning(
            "ai outcome orphaned analysis_id=%s owner_id=%s status=%s",
            analysis_id,
            owner_id,
            ai_status,
        )


def _overview_payload(detail: AnalysisDetail) -> OverviewPayload:
    """Deterministic context for the overview: top 12 findings by severity
    then position (spec §3 caps), summaries only — never full raw text."""
    ranked = sorted(
        (
            (_SEVERITY_RANK.get(issue.severity, len(_SEVERITY_RANK)), item.position, issue)
            for item in detail.requirements
            for issue in item.issues
        ),
        key=lambda entry: (entry[0], entry[1]),
    )
    return OverviewPayload(
        analysis_id=detail.id,
        score=detail.score,
        band=detail.band,
        top_findings=[_summarize(issue) for _, _, issue in ranked[:12]],
        requirements_count=detail.requirements_count,
        issues_count=detail.issues_count,
    )


def _improvement_payload(item: RequirementDetail) -> ImprovementPayload:
    """One requirement (≤4 000 chars) + its first 8 findings (spec §3 caps)."""
    return ImprovementPayload(
        requirement_text=item.text[:4000],
        findings=[_summarize(issue) for issue in item.issues[:8]],
    )


def _summarize(issue: IssueDetail) -> FindingSummary:
    """One finding minimized for AI context (pre-sliced to the §3 caps so
    Pydantic validation can never raise on engine text)."""
    return FindingSummary(
        category=issue.category[:64],
        severity=issue.severity,
        phrase=issue.phrase[:500],
        reason=issue.reason[:1000],
    )


def _apply_rewrites(
    requirements: tuple[RequirementDetail, ...], rewrites: dict[uuid.UUID, str]
) -> tuple[RequirementDetail, ...]:
    """Rebuild the requirements tuple with AI rewrites stamped in (originals
    immutable — `suggested_rewrite` is additive-only, `suggestion_source='ai'`)."""
    return tuple(
        replace(item, suggested_rewrite=rewrites[item.id], suggestion_source="ai")
        if item.id in rewrites
        else item
        for item in requirements
    )
