"use client";

/**
 * Analysis result report (Stage 09): overall score + heuristic band, severity
 * stats, category + requirement-health overviews, THEN the AI enhancement
 * outcome block (Stage 14 states; Stage 15 trust layer — disclaimer,
 * long-text disclosure, partial-coverage honesty), then the filterable /
 * sortable requirement list with collapsible explainable issues (AI
 * rewrites render inline, labeled, additive-only). Deterministic-first
 * ordering is deliberate: AI never precedes the authoritative result.
 * Shared by the fresh workspace result (`context="fresh"`) and the
 * saved-report route (`context="saved"` — the footer `actions` differ, the
 * report never does). Everything rendered is the persisted backend record —
 * no recalculation.
 */

import { useMemo, useState } from "react";
import { CircleCheck, Info, Search, TriangleAlert } from "lucide-react";

import type { AnalysisResult, RequirementSeverity } from "@/types/analysis";
import {
  DEFAULT_FILTERS,
  countByCategory,
  filterRequirements,
  sortRequirements,
  type ReportFilterState,
  type SortMode,
} from "@/lib/reporting";

import { AiOverviewSection } from "./AiOverviewSection";
import { CategoryBars } from "./CategoryBars";
import { HealthBars } from "./HealthBars";
import { RequirementCard } from "./RequirementCard";
import { ScoreRing } from "./ScoreRing";

const SEVERITIES: RequirementSeverity[] = ["low", "medium", "high", "critical"];

const SEVERITY_BAR: Record<RequirementSeverity, string> = {
  low: "bg-sev-low",
  medium: "bg-sev-medium",
  high: "bg-sev-high",
  critical: "bg-sev-critical",
};

const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "original", label: "Original order" },
  { value: "lowest-score", label: "Lowest score first" },
  { value: "most-issues", label: "Most issues first" },
];

function formatReportDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

function sourceLabel(result: AnalysisResult): string {
  if (result.document !== null) {
    return `File ${result.document.filename} (${result.document.file_type.toUpperCase()})`;
  }
  return "Pasted SRS text";
}

function severityMixLabel(counts: Record<RequirementSeverity, number>): string {
  const parts = SEVERITIES.filter((severity) => counts[severity] > 0).map(
    (severity) => `${counts[severity]} ${severity}`,
  );
  return `Severity mix: ${parts.join(", ")}`;
}

export function AnalysisResultView({
  result,
  context = "fresh",
  actions,
  onAiRetried,
}: {
  result: AnalysisResult;
  /** "fresh" = just analyzed in the workspace; "saved" = opened report route. */
  context?: "fresh" | "saved";
  /** Footer actions (Start over for fresh; Back + Delete for saved). */
  actions?: React.ReactNode;
  /** AI-retry refresh (Stage 17): re-read the detail after a retry POST.
   * Absent → the failed AI card renders buttonless (no fake controls). */
  onAiRetried?: (analysisId: string) => Promise<unknown>;
}) {
  const [filters, setFilters] = useState<ReportFilterState>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortMode>("original");
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(new Set());

  const requirements = result.requirements.length;
  const counts = result.score_breakdown?.counts;
  const eyebrowKind = context === "fresh" ? "Analysis complete" : "Saved analysis";
  const metaVerb = context === "fresh" ? "Analyzed" : "Saved";

  const categories = useMemo(() => countByCategory(result.requirements), [result.requirements]);
  const visible = useMemo(
    () => sortRequirements(filterRequirements(result.requirements, filters), sort),
    [result.requirements, filters, sort],
  );
  const allExpanded =
    visible.length > 0 && visible.every((requirement) => expandedIds.has(requirement.id));
  // Stage 15: persisted rewrite coverage for the AI block's partial-honesty
  // note — derived from the record (flagged vs rewritten counts), never
  // invented. Only meaningful on `ok` runs; every other state passes null.
  const rewriteCoverage = useMemo(() => {
    if (result.ai_status !== "ok") return null;
    let rewritten = 0;
    let flagged = 0;
    for (const requirement of result.requirements) {
      if (requirement.suggested_rewrite !== null) rewritten += 1;
      if (requirement.issues.length > 0) flagged += 1;
    }
    return { rewritten, flagged };
  }, [result.ai_status, result.requirements]);

  function toggleRequirement(id: string) {
    setExpandedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleExpandAll() {
    if (allExpanded) setExpandedIds(new Set());
    else setExpandedIds(new Set(visible.map((requirement) => requirement.id)));
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
    setSort("original");
  }

  if (result.status === "failed") {
    return (
      <section aria-labelledby="analysis-result-heading" className="mt-8">
        <p className="font-mono text-xs tracking-[0.2em] text-critic uppercase">
          {context === "fresh" ? "Analysis failed" : "Saved analysis · failed"}
        </p>
        <h2 id="analysis-result-heading" className="mt-2 text-2xl font-semibold tracking-[-0.02em]">
          {result.title}
        </h2>
        <div className="mt-6 rounded-card border border-critic/40 bg-paper p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 size-5 shrink-0 text-critic" aria-hidden />
            <div>
              <h3 className="text-lg font-semibold tracking-[-0.01em]">
                This analysis did not complete
              </h3>
              <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
                No scores or issues are shown because none were produced. Re-run the analysis from
                the Analyzer; if the failure repeats, the input may exceed the supported limits.
              </p>
            </div>
          </div>
        </div>
        {actions ? <div className="mt-6 flex flex-wrap gap-3">{actions}</div> : null}
      </section>
    );
  }

  const selectClassName =
    "w-full rounded-lg border border-line bg-white px-2.5 py-2 text-sm text-ink outline-none transition focus-visible:ring-2 focus-visible:ring-signal/50";
  const labelClassName = "font-mono text-[11px] tracking-[0.12em] text-ink-faint uppercase";

  return (
    <section aria-labelledby="analysis-result-heading" className="mt-8">
      <p className="font-mono text-xs tracking-[0.2em] text-signal uppercase">
        {`${eyebrowKind} · ${requirements} ${requirements === 1 ? "requirement" : "requirements"} · ${result.issues_count} ${result.issues_count === 1 ? "issue" : "issues"}`}
      </p>
      <h2 id="analysis-result-heading" className="mt-2 text-2xl font-semibold tracking-[-0.02em]">
        {result.title}
      </h2>
      <p className="mt-2 font-mono text-xs text-ink-faint">
        {`${metaVerb} ${formatReportDate(result.created_at)} · ${sourceLabel(result)}`}
      </p>

      <div className="mt-6 rounded-card border border-line bg-paper p-5 sm:p-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <ScoreRing score={result.score} band={result.band} />
          <dl className="grid grid-cols-2 gap-x-10 gap-y-3 sm:grid-cols-2">
            <div>
              <dt className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase">
                Requirements
              </dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums">
                {result.requirements_count}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase">
                Issues
              </dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums">{result.issues_count}</dd>
            </div>
            {SEVERITIES.map((severity) => (
              <div key={severity}>
                <dt className="font-mono text-[11px] tracking-[0.14em] text-ink-faint capitalize">
                  {severity}
                </dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums">
                  {counts?.[severity] ?? 0}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        {result.issues_count > 0 && counts !== undefined && counts !== null ? (
          <div
            role="img"
            aria-label={severityMixLabel(counts)}
            className="mt-5 flex h-2 overflow-hidden rounded-full bg-paper-deep"
          >
            {SEVERITIES.filter((severity) => counts[severity] > 0).map((severity) => (
              <span
                key={severity}
                aria-hidden
                className={SEVERITY_BAR[severity]}
                style={{ width: `${(counts[severity] / result.issues_count) * 100}%` }}
              />
            ))}
          </div>
        ) : null}
        <p className="mt-5 border-t border-line pt-4 text-[13px] leading-relaxed text-ink-faint">
          The score is a transparent heuristic indicator — 100 minus fixed deductions per issue —
          not a scientifically validated measurement of requirement quality.
        </p>
      </div>

      {result.status === "segmented" ? (
        <div
          role="status"
          className="mt-6 flex items-start gap-3 rounded-card border border-gold/50 bg-gold/10 p-4"
        >
          <Info className="mt-0.5 size-5 shrink-0 text-gold" aria-hidden />
          <p className="text-sm leading-relaxed text-ink-soft">
            Scored with an older version — requirements are listed without scores or severities.
            Re-run from the Analyzer for a full result.
          </p>
        </div>
      ) : null}

      {result.status === "analyzed" && result.issues_count === 0 ? (
        <div
          role="status"
          className="mt-6 flex items-start gap-3 rounded-card border border-sev-low/40 bg-sev-low/10 p-4"
        >
          <CircleCheck className="mt-0.5 size-5 shrink-0 text-sev-low" aria-hidden />
          <div>
            <h3 className="text-[15px] font-semibold">No ambiguity issues detected</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink-soft">
              The deterministic detector did not identify any supported ambiguity patterns in these
              requirements. The score stays a heuristic indicator — human review still applies.
            </p>
          </div>
        </div>
      ) : null}

      {result.status === "analyzed" &&
      result.issues_count > 0 &&
      (categories.length > 0 || result.health !== null) ? (
        <div className="mt-6 grid gap-6 rounded-card border border-line bg-paper p-5 sm:grid-cols-2 sm:p-6">
          <CategoryBars counts={categories} />
          {result.health !== null ? <HealthBars health={result.health} /> : null}
        </div>
      ) : null}

      <AiOverviewSection
        status={result.ai_status}
        overview={result.ai_overview}
        provider={result.ai_provider}
        error={result.ai_error}
        rewriteCoverage={rewriteCoverage}
        retry={
          onAiRetried === undefined
            ? null
            : { analysisId: result.id, onRetried: () => onAiRetried(result.id) }
        }
      />

      {result.requirements.length >= 2 ? (
        <div className="mt-6 rounded-card border border-line bg-paper p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
            <div className="min-w-0 flex-1">
              <label htmlFor="report-search" className={labelClassName}>
                Search
              </label>
              <div className="relative mt-1.5">
                <Search
                  aria-hidden
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint"
                />
                <input
                  id="report-search"
                  type="search"
                  value={filters.query}
                  onChange={(event) =>
                    setFilters((previous) => ({ ...previous, query: event.target.value }))
                  }
                  placeholder="Search text or ID…"
                  className="w-full rounded-lg border border-line bg-white py-2 pr-3 pl-9 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-signal/50"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:w-auto">
              <div>
                <label htmlFor="report-filter-status" className={labelClassName}>
                  Status
                </label>
                <select
                  id="report-filter-status"
                  value={filters.status}
                  onChange={(event) =>
                    setFilters((previous) => ({
                      ...previous,
                      status: event.target.value as ReportFilterState["status"],
                    }))
                  }
                  className={`${selectClassName} mt-1.5`}
                >
                  <option value="all">All</option>
                  <option value="with-issues">With issues</option>
                  <option value="clean">Clean</option>
                </select>
              </div>
              <div>
                <label htmlFor="report-filter-severity" className={labelClassName}>
                  Severity
                </label>
                <select
                  id="report-filter-severity"
                  value={filters.severity}
                  onChange={(event) =>
                    setFilters((previous) => ({
                      ...previous,
                      severity: event.target.value as ReportFilterState["severity"],
                    }))
                  }
                  className={`${selectClassName} mt-1.5`}
                >
                  <option value="all">All</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label htmlFor="report-sort" className={labelClassName}>
                  Sort
                </label>
                <select
                  id="report-sort"
                  value={sort}
                  onChange={(event) => setSort(event.target.value as SortMode)}
                  className={`${selectClassName} mt-1.5`}
                >
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
            <p aria-live="polite" aria-atomic="true" className="font-mono text-xs text-ink-faint">
              {visible.length === requirements
                ? `Showing all ${requirements} requirements`
                : `Showing ${visible.length} of ${requirements} requirements`}
            </p>
            <button
              type="button"
              onClick={toggleExpandAll}
              className="rounded-full px-3 py-1.5 font-mono text-xs font-medium text-signal transition outline-none hover:bg-signal/10 focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              {allExpanded ? "Collapse all" : "Expand all"}
            </button>
          </div>
        </div>
      ) : null}

      {visible.length > 0 ? (
        <ol className="mt-6 space-y-3">
          {visible.map((requirement, index) => (
            <RequirementCard
              key={requirement.id}
              requirement={requirement}
              index={index}
              expanded={expandedIds.has(requirement.id)}
              onToggle={() => toggleRequirement(requirement.id)}
            />
          ))}
        </ol>
      ) : (
        <div className="mt-6 rounded-card border border-dashed border-line bg-paper p-6 text-center">
          <h3 className="text-[15px] font-semibold">No requirements match</h3>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">
            Try clearing the search or resetting the filters.
          </p>
          <button
            type="button"
            onClick={resetFilters}
            className="mt-4 inline-flex items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
          >
            Reset filters
          </button>
        </div>
      )}

      {actions ? <div className="mt-6 flex flex-wrap gap-3">{actions}</div> : null}
    </section>
  );
}
