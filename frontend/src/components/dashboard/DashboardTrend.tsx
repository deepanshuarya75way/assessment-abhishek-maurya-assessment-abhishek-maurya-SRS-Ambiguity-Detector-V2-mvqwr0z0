"use client";

/**
 * Score-trend section (Stage 11): the documented range control (30 days / 12
 * weeks — the ONLY ranges, per contract §4.5), the Recharts visual (lazy,
 * client-only), a real-text legend, a spoken summary, and the full bucket
 * table. Buckets are UTC days / Monday-start UTC weeks, zero-filled: empty
 * buckets render as gaps and "—", never as fake zeros.
 */

import dynamic from "next/dynamic";
import { useId, useMemo } from "react";

import type { DashboardRange, DashboardTrendBucket } from "@/types/dashboard";

import type { TrendPoint } from "./TrendChart";

const TrendChart = dynamic(() => import("./TrendChart").then((module) => module.TrendChart), {
  ssr: false,
  loading: () => (
    <div aria-hidden className="h-64 animate-pulse rounded-card bg-paper-deep/70 sm:h-72" />
  ),
});

const RANGE_OPTIONS: Array<{ value: DashboardRange; label: string }> = [
  { value: "30d", label: "Last 30 days" },
  { value: "12w", label: "Last 12 weeks" },
];

function formatBucketDay(bucket: string): string {
  return new Date(`${bucket}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function toPoints(buckets: DashboardTrendBucket[], range: DashboardRange): TrendPoint[] {
  return buckets.map((bucket) => {
    const day = formatBucketDay(bucket.bucket);
    return {
      key: bucket.bucket,
      label: day,
      fullLabel: range === "12w" ? `Week of ${day}` : day,
      avg: bucket.avg_score,
      analyses: bucket.analyses,
      requirements: bucket.requirements,
    };
  });
}

export function DashboardTrend({
  range,
  onRange,
  buckets,
  improved,
  scored,
  stale,
}: {
  range: DashboardRange;
  onRange: (range: DashboardRange) => void;
  buckets: DashboardTrendBucket[];
  improved: number;
  scored: number;
  stale: boolean;
}) {
  const headingId = useId();
  const points = useMemo(() => toPoints(buckets, range), [buckets, range]);
  const { windowRuns, scoredBuckets } = useMemo(
    () => ({
      windowRuns: buckets.reduce((total, bucket) => total + bucket.analyses, 0),
      scoredBuckets: buckets.filter((bucket) => bucket.avg_score !== null).length,
    }),
    [buckets],
  );
  const windowLabel =
    range === "30d" ? "daily buckets (UTC)" : "weekly buckets (UTC, weeks start Monday)";
  const summary =
    `Ambiguity score over time, ${windowLabel}. ` +
    `${windowRuns} ${windowRuns === 1 ? "run" : "runs"} in this window across ` +
    `${scoredBuckets} ${scoredBuckets === 1 ? "bucket" : "buckets"} with scored runs.`;

  return (
    <section
      aria-labelledby={headingId}
      aria-busy={stale}
      className={stale ? "opacity-60 transition-opacity" : "transition-opacity"}
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2
            id={headingId}
            className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
          >
            Ambiguity score over time
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
            Average persisted score per bucket — {windowLabel}.
          </p>
        </div>
        <div
          role="group"
          aria-label="Trend range"
          className="inline-flex rounded-full border border-line bg-paper p-1"
        >
          {RANGE_OPTIONS.map((option) => {
            const active = option.value === range;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                onClick={() => onRange(option.value)}
                className={
                  active
                    ? "rounded-full bg-ink px-3.5 py-1.5 text-sm font-medium text-paper transition outline-none focus-visible:ring-2 focus-visible:ring-signal/50"
                    : "rounded-full px-3.5 py-1.5 text-sm font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
                }
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>

      {windowRuns === 0 ? (
        <p className="mt-4 rounded-card border border-dashed border-line bg-paper p-5 text-sm leading-relaxed text-ink-soft">
          None of your runs fall inside this window — the table below shows the empty buckets.
          Switch ranges to look further back.
        </p>
      ) : (
        <div className="mt-4">
          <ul aria-label="Chart legend" className="flex flex-wrap gap-x-5 gap-y-1">
            <li className="inline-flex items-center gap-2 font-mono text-xs text-ink-soft">
              <span aria-hidden className="h-0.5 w-5 rounded-full bg-signal" />
              Average score (0–100)
            </li>
            <li className="inline-flex items-center gap-2 font-mono text-xs text-ink-soft">
              <span aria-hidden className="h-2.5 w-2.5 rounded-[3px] bg-line" />
              Runs per bucket
            </li>
          </ul>
          <div role="img" aria-label={summary} className="mt-3">
            <div aria-hidden>
              <TrendChart points={points} />
            </div>
          </div>
        </div>
      )}

      <details className="mt-4 rounded-card border border-line bg-paper">
        <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-ink-soft outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50">
          View trend data as a table
        </summary>
        <div className="overflow-x-auto px-5 pb-5">
          <table className="w-full text-sm tabular-nums">
            <caption className="sr-only">
              Per-bucket average score, run count, and requirement count — {windowLabel}
            </caption>
            <thead>
              <tr className="border-b border-line text-left font-mono text-[11px] tracking-[0.1em] text-ink-faint uppercase">
                <th scope="col" className="py-2 pr-4 font-medium">
                  {range === "12w" ? "Week of" : "Day"}
                </th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">
                  Average score
                </th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">
                  Runs
                </th>
                <th scope="col" className="py-2 text-right font-medium">
                  Requirements
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {points.map((point) => (
                <tr key={point.key}>
                  <th scope="row" className="py-2 pr-4 text-left font-normal text-ink">
                    {point.fullLabel}
                  </th>
                  <td className="py-2 pr-4 text-right text-ink-soft">
                    {point.avg === null ? "—" : point.avg}
                  </td>
                  <td className="py-2 pr-4 text-right text-ink-soft">{point.analyses}</td>
                  <td className="py-2 text-right text-ink-soft">{point.requirements}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <p className="mt-3 text-[13px] leading-relaxed text-ink-faint">
        {scored === 0
          ? "No scored runs to compare yet — each scored run is measured against the previous one."
          : `${improved} of ${scored} scored ${scored === 1 ? "run" : "runs"} scored above the previous run.`}
      </p>
    </section>
  );
}
