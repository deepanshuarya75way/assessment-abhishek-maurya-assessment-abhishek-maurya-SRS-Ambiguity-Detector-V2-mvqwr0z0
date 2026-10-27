"use client";

/**
 * AI enhancement outcome block (Stage 14): one of four honest states driven
 * by `ai_status` — generated overview with provider attribution (`ok`),
 * user-safe error card (`failed` — deterministic findings stay visible, with
 * a Retry button once the caller passes `retry`, Stage 17), empty state +
 * Settings CTA (`unconfigured`), or a neutral one-liner (`skipped`). Renders
 * nothing structural the deterministic report depends on: AI is additive-only.
 *
 * Text discipline: `overview`/`error` render as PLAIN TEXT (React-escaped —
 * model output is untrusted by contract). Unknown provider ids degrade to
 * unattributed rendering (drift never crashes the report).
 *
 * Stage 15 trust layer: the `ok` state carries an explicit review
 * disclaimer, long overviews clamp behind an accessible Show more/less
 * disclosure (length-capped model output can still run long), and partial
 * rewrite coverage renders an honest derived note (the backend is
 * best-effort per requirement — `rewriteCoverage` counts come from the
 * persisted record, never invented).
 *
 * Stage 17 retry: the failed card owns the POST (pending + code-mapped
 * error + session-gone sign-in link) while the PARENT owns the refresh —
 * on success the caller re-reads the detail (fresh rewrites included) and
 * this block re-renders from the new record. No retry prop, no button
 * (a button with nowhere to refresh to would be a fake control).
 */

import { useId, useState } from "react";
import Link from "next/link";
import { Bot, CircleAlert, Loader2, RotateCw, Settings2 } from "lucide-react";

import type { AiStatus } from "@/types/analysis";
import { PROVIDER_DISPLAY_NAMES, isProviderId } from "@/types/providers";
import { retryAi } from "@/lib/analysis";
import { analysisErrorMessage } from "@/lib/analysis-errors";
import { isSessionGone } from "@/lib/auth";
import { cn } from "@/lib/utils";

/** Overviews longer than this clamp behind the Show more disclosure. */
const LONG_OVERVIEW_CHARS = 600;

function attribution(provider: string | null): string | null {
  if (!isProviderId(provider)) return null;
  return PROVIDER_DISPLAY_NAMES[provider];
}

function RetryControl({
  analysisId,
  onRetried,
}: {
  analysisId: string;
  onRetried: () => Promise<unknown>;
}) {
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [sessionGone, setSessionGone] = useState(false);

  async function handleRetry() {
    if (pending) return;
    setPending(true);
    setFailure(null);
    setSessionGone(false);
    try {
      await retryAi(analysisId);
      // The POST landed — the new record (status + rewrites) arrives via the
      // parent's refresh. A refresh failure keeps THIS card (still honest:
      // the retry happened, the view just didn't update) with a retryable error.
      await onRetried();
    } catch (err) {
      if (isSessionGone(err)) setSessionGone(true);
      setFailure(err);
      setPending(false);
      return;
    }
    setPending(false);
  }

  return (
    <div className="mt-3">
      {failure !== null ? (
        <p role="alert" className="text-sm leading-relaxed text-critic">
          {sessionGone ? (
            <>
              Your session expired before the retry finished.{" "}
              <Link
                href="/login"
                className="font-semibold underline underline-offset-2 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-critic/40"
              >
                Sign in again
              </Link>
            </>
          ) : (
            analysisErrorMessage(failure)
          )}
        </p>
      ) : null}
      <button
        type="button"
        onClick={handleRetry}
        disabled={pending}
        className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-line px-4 py-1.5 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
      >
        {pending ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Retrying…
          </>
        ) : (
          <>
            <RotateCw className="size-4" aria-hidden />
            Try again
          </>
        )}
      </button>
    </div>
  );
}

export function AiOverviewSection({
  status,
  overview,
  provider,
  error,
  rewriteCoverage = null,
  retry = null,
}: {
  status: AiStatus;
  overview: string | null;
  provider: string | null;
  error: string | null;
  /** Persisted rewrite counts (Stage 15): `{rewritten, flagged}` derived by
   * the parent from the requirements list — `null` unless `status` is `ok`. */
  rewriteCoverage?: { rewritten: number; flagged: number } | null;
  /** Retry wiring (Stage 17): the persisted analysis id + the parent's
   * detail refresh. Absent → the failed card renders buttonless (as before). */
  retry?: { analysisId: string; onRetried: () => Promise<unknown> } | null;
}) {
  // Hooks run unconditionally (rules-of-hooks) — only the `ok` branch uses them.
  const [expanded, setExpanded] = useState(false);
  const overviewId = useId();
  if (status === "skipped") {
    return (
      <p role="status" className="mt-6 font-mono text-xs text-ink-faint">
        AI enhancement was off for this run — deterministic results only.
      </p>
    );
  }

  if (status === "unconfigured") {
    return (
      <div className="mt-6 rounded-card border border-dashed border-line bg-paper p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <Bot className="mt-0.5 size-5 shrink-0 text-ink-faint" aria-hidden />
          <div>
            <h3 className="text-[15px] font-semibold">AI enhancement isn&apos;t configured yet</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink-soft">
              Add your own provider key to get an AI-written overview plus per-requirement rewrites
              on future runs. Deterministic scores and issues work without it.
            </p>
            <Link
              href="/settings"
              className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-line px-4 py-1.5 text-sm font-medium text-ink-soft transition hover:bg-paper-deep"
            >
              <Settings2 className="size-4" aria-hidden />
              Open Settings
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="mt-6 rounded-card border border-critic/40 bg-paper p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <CircleAlert className="mt-0.5 size-5 shrink-0 text-critic" aria-hidden />
          <div className="min-w-0 flex-1">
            <h3 className="text-[15px] font-semibold">AI enhancement failed</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink-soft">
              {error ?? "The AI step did not complete."}
            </p>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-faint">
              Deterministic scores and issues above are unaffected — only the AI overview and
              rewrites are missing.
            </p>
            {retry !== null ? (
              <RetryControl analysisId={retry.analysisId} onRetried={retry.onRetried} />
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  const byline = attribution(provider);
  const text = overview ?? "No overview text was returned.";
  const clamped = !expanded && text.length > LONG_OVERVIEW_CHARS;
  const partial = rewriteCoverage !== null && rewriteCoverage.flagged > rewriteCoverage.rewritten;
  return (
    <div className="mt-6 rounded-card border border-line bg-paper p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <Bot className="mt-0.5 size-5 shrink-0 text-signal" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold">AI overview</h3>
          {byline ? (
            <p className="mt-0.5 font-mono text-xs text-ink-faint">Generated by {byline}</p>
          ) : null}
          <p
            id={overviewId}
            className={cn(
              "mt-2 text-[15px] leading-relaxed whitespace-pre-wrap text-ink-soft",
              clamped && "line-clamp-6",
            )}
          >
            {text}
          </p>
          {text.length > LONG_OVERVIEW_CHARS ? (
            <button
              type="button"
              onClick={() => setExpanded((open) => !open)}
              aria-expanded={expanded}
              aria-controls={overviewId}
              className="mt-2 rounded-full px-3 py-1.5 font-mono text-xs font-medium text-signal transition outline-none hover:bg-signal/10 focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          ) : null}
          {partial && rewriteCoverage ? (
            <p role="status" className="mt-2 font-mono text-xs text-ink-faint">
              {`AI rewrites cover ${rewriteCoverage.rewritten} of ${rewriteCoverage.flagged} flagged requirement${rewriteCoverage.flagged === 1 ? "" : "s"}.`}
            </p>
          ) : null}
          <p className="mt-3 border-t border-line pt-3 text-[13px] leading-relaxed text-ink-faint">
            AI-generated enrichment — review suggestions against the original requirements and
            project context before applying them. To generate this run, the app sent finding
            summaries for the overview and only flagged requirement excerpts for rewrites; provider
            retention follows that provider&apos;s policy.
          </p>
        </div>
      </div>
    </div>
  );
}
