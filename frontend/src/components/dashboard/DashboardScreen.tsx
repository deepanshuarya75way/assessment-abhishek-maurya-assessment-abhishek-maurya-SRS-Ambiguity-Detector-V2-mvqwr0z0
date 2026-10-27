"use client";

/**
 * Analytics dashboard (Stage 11): the authenticated user's persisted history
 * as server-computed aggregates — totals, averages, band/source/category/
 * severity distributions, a UTC-bucketed score trend, and recent runs. The
 * snapshot renders VERBATIM: no score, band, or severity is ever derived in
 * this file (averages arrive rounded, bands arrive persisted, severities
 * arrive counted). States mirror history: loading skeleton, session-gone
 * sign-in nudge, code-mapped error + retry, deliberate first-use panel for
 * empty accounts, and honest partial-data notes (unscored runs, zero issues).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Inbox, TriangleAlert } from "lucide-react";

import { CategoryBars } from "@/components/analyzer/CategoryBars";
import { BAND_LABELS, ScoreRing } from "@/components/analyzer/ScoreRing";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { Container } from "@/components/layout/Container";
import { Reveal } from "@/components/Reveal";
import { analysisErrorMessage } from "@/lib/analysis-errors";
import { getDashboard } from "@/lib/dashboard";
import { isSessionGone } from "@/lib/auth";
import type { AnalysisBand } from "@/types/analysis";
import type { DashboardSnapshot, DashboardRange } from "@/types/dashboard";

import { DashboardTrend } from "./DashboardTrend";
import { RecentAnalyses } from "./RecentAnalyses";
import { SeverityMix } from "./SeverityMix";

const UNEXPECTED_RESPONSE = "The service returned an unexpected response.";

type LoadState =
  | { status: "loading" }
  | { status: "session-gone" }
  | { status: "load-failed"; message: string }
  | { status: "ready"; snapshot: DashboardSnapshot };

function isDashboardSnapshot(data: unknown): data is DashboardSnapshot {
  if (typeof data !== "object" || data === null) return false;
  const snapshot = data as Record<string, unknown>;
  return (
    (snapshot.range === "30d" || snapshot.range === "12w") &&
    typeof snapshot.stats === "object" &&
    snapshot.stats !== null &&
    Array.isArray(snapshot.bands) &&
    Array.isArray(snapshot.sources) &&
    Array.isArray(snapshot.categories) &&
    Array.isArray(snapshot.severity) &&
    Array.isArray(snapshot.trend) &&
    Array.isArray(snapshot.recent)
  );
}

/** Band dots mirror ScoreRing's band colors (labels always carry meaning). */
const BAND_DOT: Record<AnalysisBand, string> = {
  low: "bg-signal",
  moderate: "bg-sev-medium",
  high: "bg-sev-high",
  very_high: "bg-sev-critical",
};

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function formatRunDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

function BackLink() {
  return (
    <Link
      href="/analyzer"
      className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
    >
      <ArrowLeft className="size-3.5" aria-hidden />
      Analyzer
    </Link>
  );
}

function StatCell({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <dt className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase">{label}</dt>
      <dd className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">{value}</dd>
      <dd className="mt-1 text-[13px] leading-snug text-ink-faint">{sub}</dd>
    </div>
  );
}

function DashboardContent() {
  const [range, setRange] = useState<DashboardRange>("30d");
  const [refreshKey, setRefreshKey] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getDashboard(range).then(
      (data) => {
        if (cancelled) return;
        if (!isDashboardSnapshot(data)) {
          setState({ status: "load-failed", message: UNEXPECTED_RESPONSE });
          return;
        }
        setState({ status: "ready", snapshot: data });
      },
      (err: unknown) => {
        if (cancelled) return;
        if (isSessionGone(err)) setState({ status: "session-gone" });
        else setState({ status: "load-failed", message: analysisErrorMessage(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [range, refreshKey]);

  const stale = state.status === "ready" && state.snapshot.range !== range;
  const snapshot = state.status === "ready" ? state.snapshot : null;

  return (
    <Container className="py-10 sm:py-14">
      <BackLink />
      <Reveal>
        <p className="mt-4 font-mono text-xs tracking-[0.2em] text-signal uppercase">Dashboard</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.02em] text-balance sm:text-4xl">
          Dashboard
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-soft">
          Aggregate statistics across your saved analyses — computed server-side from your persisted
          history.
        </p>
      </Reveal>

      {state.status === "loading" ? (
        <div
          aria-busy="true"
          aria-label="Loading dashboard"
          className="mt-8 rounded-card border border-line bg-paper p-8"
        >
          <div className="animate-pulse space-y-3">
            <div className="h-6 w-48 rounded-lg bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-2/3 rounded bg-paper-deep" />
          </div>
        </div>
      ) : null}

      {state.status === "session-gone" ? (
        <div role="status" className="mt-8 max-w-xl">
          <h2 className="text-2xl font-semibold tracking-[-0.02em]">Session expired</h2>
          <p className="mt-3 text-base leading-relaxed text-ink-soft">
            Sign in again to view your dashboard.
          </p>
          <p className="mt-5">
            <Link
              href="/login"
              className="inline-flex items-center justify-center rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Sign in
            </Link>
          </p>
        </div>
      ) : null}

      {state.status === "load-failed" ? (
        <div
          role="alert"
          className="mt-8 flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
        >
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-gold" aria-hidden />
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.01em]">
              Couldn&apos;t load your dashboard
            </h2>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">{state.message}</p>
            <button
              type="button"
              onClick={() => {
                setState({ status: "loading" });
                setRefreshKey((count) => count + 1);
              }}
              className="mt-4 inline-flex items-center justify-center rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Retry
            </button>
          </div>
        </div>
      ) : null}

      {snapshot !== null && snapshot.stats.analyses_total === 0 ? (
        <div
          role="status"
          className="mt-8 flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
        >
          <Inbox className="mt-0.5 size-5 shrink-0 text-ink-faint" aria-hidden />
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.01em]">No analyses yet</h2>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
              Your dashboard will summarize scores, trends, and issue patterns once you run your
              first analysis.
            </p>
            <p className="mt-4">
              <Link
                href="/analyzer"
                className="inline-flex items-center justify-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
              >
                Analyze requirements
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </p>
          </div>
        </div>
      ) : null}

      {snapshot !== null && snapshot.stats.analyses_total > 0 ? (
        <div className="mt-8 space-y-10">
          <Reveal>
            <section aria-label="Totals">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-6 lg:grid-cols-4">
                <StatCell
                  label="Analyses"
                  value={String(snapshot.stats.analyses_total)}
                  sub={`${plural(snapshot.stats.analyses_scored, "run", "runs")} scored`}
                />
                <StatCell
                  label="Average score"
                  value={snapshot.stats.avg_score === null ? "—" : String(snapshot.stats.avg_score)}
                  sub={
                    snapshot.stats.analyses_scored === 0
                      ? "no scored runs yet"
                      : `across ${plural(snapshot.stats.analyses_scored, "scored run", "scored runs")}`
                  }
                />
                <StatCell
                  label="Requirements"
                  value={String(snapshot.stats.requirements_total)}
                  sub="analyzed in total"
                />
                <StatCell
                  label="Issues"
                  value={String(snapshot.stats.issues_total)}
                  sub="found in total"
                />
              </dl>
              <p className="mt-4 font-mono text-xs text-ink-faint">
                {snapshot.sources
                  .map((entry) =>
                    entry.source_type === "text"
                      ? `${plural(entry.count, "run", "runs")} from pasted text`
                      : `${plural(entry.count, "run", "runs")} from file uploads`,
                  )
                  .join(" · ")}
              </p>
            </section>
          </Reveal>

          <Reveal>
            <div className="rounded-card border border-line bg-paper p-5 sm:p-6">
              <DashboardTrend
                range={range}
                onRange={setRange}
                buckets={snapshot.trend}
                improved={snapshot.stats.improved_count}
                scored={snapshot.stats.analyses_scored}
                stale={stale}
              />
            </div>
          </Reveal>

          <div className="grid gap-6 lg:grid-cols-2">
            <Reveal>
              <div className="h-full rounded-card border border-line bg-paper p-5 sm:p-6">
                <section aria-labelledby="dashboard-latest">
                  <h2
                    id="dashboard-latest"
                    className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
                  >
                    Latest run
                  </h2>
                  {snapshot.stats.latest !== null ? (
                    <div className="mt-4">
                      <ScoreRing
                        score={snapshot.stats.latest.score}
                        band={snapshot.stats.latest.band}
                      />
                      <p className="mt-4">
                        <Link
                          href={`/analysis/${snapshot.stats.latest.id}`}
                          title={snapshot.stats.latest.title}
                          className="text-[15px] font-semibold [overflow-wrap:anywhere] text-ink underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-signal/50"
                        >
                          {snapshot.stats.latest.title}
                        </Link>
                      </p>
                      <p className="mt-1 font-mono text-xs text-ink-faint">
                        {formatRunDate(snapshot.stats.latest.created_at)}
                      </p>
                    </div>
                  ) : null}
                </section>
              </div>
            </Reveal>
            <Reveal delay={0.06}>
              <div className="h-full rounded-card border border-line bg-paper p-5 sm:p-6">
                <section aria-labelledby="dashboard-bands">
                  <h2
                    id="dashboard-bands"
                    className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
                  >
                    Score bands
                  </h2>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
                    Scored runs per persisted band.
                  </p>
                  <ul className="mt-4 space-y-2.5">
                    {snapshot.bands.map((entry) => (
                      <li
                        key={entry.band}
                        className="flex items-baseline justify-between gap-3 text-sm"
                      >
                        <span className="inline-flex min-w-0 items-center gap-2">
                          <span
                            aria-hidden
                            className={`size-2 shrink-0 rounded-full ${BAND_DOT[entry.band]}`}
                          />
                          <span className="truncate font-medium text-ink">
                            {BAND_LABELS[entry.band]}
                          </span>
                        </span>
                        <span className="shrink-0 font-mono text-[13px] text-ink-soft tabular-nums">
                          {entry.count}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 text-[13px] leading-relaxed text-ink-faint">
                    {snapshot.stats.high_risk_count === 0
                      ? "No runs in high bands."
                      : `${plural(snapshot.stats.high_risk_count, "run", "runs")} in high bands.`}
                  </p>
                </section>
              </div>
            </Reveal>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Reveal>
              <div className="h-full rounded-card border border-line bg-paper p-5 sm:p-6">
                {snapshot.categories.length === 0 ? (
                  <section aria-labelledby="dashboard-categories-empty">
                    <h2
                      id="dashboard-categories-empty"
                      className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
                    >
                      Issue categories
                    </h2>
                    <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                      No issue categories yet — they will appear here once your runs surface some.
                    </p>
                  </section>
                ) : (
                  <CategoryBars
                    counts={snapshot.categories}
                    headingLevel="h2"
                    caption={
                      snapshot.stats.top_category === null
                        ? "Across all your analyses."
                        : `Across all your analyses — most frequent: ${snapshot.stats.top_category.category} (${snapshot.stats.top_category.count} of ${snapshot.stats.issues_total}).`
                    }
                  />
                )}
              </div>
            </Reveal>
            <Reveal delay={0.06}>
              <div className="h-full rounded-card border border-line bg-paper p-5 sm:p-6">
                <SeverityMix counts={snapshot.severity} total={snapshot.stats.issues_total} />
              </div>
            </Reveal>
          </div>

          <Reveal>
            <div className="rounded-card border border-line bg-paper p-5 sm:p-6">
              <RecentAnalyses items={snapshot.recent} />
            </div>
          </Reveal>

          <Reveal>
            <p className="max-w-2xl text-[13px] leading-relaxed text-ink-faint">
              Averages summarize your persisted heuristic scores — ranking aids for triage, not
              validated measurements. Unscored runs count toward totals but never toward averages or
              bands.
            </p>
            <p className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
              <Link
                href="/analyzer"
                className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
              >
                Analyze requirements
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
              <Link
                href="/history"
                className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
              >
                View full history
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </p>
          </Reveal>
        </div>
      ) : null}
    </Container>
  );
}

export function DashboardScreen() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}
