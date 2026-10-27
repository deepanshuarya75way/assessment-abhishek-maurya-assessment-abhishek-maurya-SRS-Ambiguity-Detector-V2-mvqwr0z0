"use client";

/**
 * Account-wide issue-severity distribution (Stage 11 dashboard section).
 * Same §7 language as the report's stacked bar (`sev-*` tokens, `role="img"`
 * + text alternative) but over server aggregates, not one analysis: the
 * counts below are real text (complete vocabulary, zeros included) while
 * the bar itself is aria-hidden decoration. Zero issues → an honest note
 * instead of a hollow bar.
 */

import { useId } from "react";

import type { RequirementSeverity } from "@/types/analysis";
import type { DashboardSeverityCount } from "@/types/dashboard";

const SEVERITIES: RequirementSeverity[] = ["low", "medium", "high", "critical"];

const SEVERITY_BAR: Record<RequirementSeverity, string> = {
  low: "bg-sev-low",
  medium: "bg-sev-medium",
  high: "bg-sev-high",
  critical: "bg-sev-critical",
};

const SEVERITY_LABEL: Record<RequirementSeverity, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

function severityMixLabel(counts: Record<RequirementSeverity, number>): string {
  const parts = SEVERITIES.filter((severity) => counts[severity] > 0).map(
    (severity) => `${counts[severity]} ${severity}`,
  );
  return `Severity mix: ${parts.join(", ")}`;
}

export function SeverityMix({
  counts,
  total,
}: {
  counts: DashboardSeverityCount[];
  total: number;
}) {
  const headingId = useId();
  const bySeverity: Record<RequirementSeverity, number> = {
    low: 0,
    medium: 0,
    high: 0,
    critical: 0,
  };
  for (const entry of counts) bySeverity[entry.severity] = entry.count;
  return (
    <section aria-labelledby={headingId}>
      <h2
        id={headingId}
        className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
      >
        Issue severity
      </h2>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
        Every issue across all your analyses.
      </p>
      {total === 0 ? (
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          No issues found across your analyses yet — clean runs stay visible here as zeros.
        </p>
      ) : (
        <div
          role="img"
          aria-label={severityMixLabel(bySeverity)}
          className="mt-4 flex h-2 overflow-hidden rounded-full bg-paper-deep"
        >
          {SEVERITIES.filter((severity) => bySeverity[severity] > 0).map((severity) => (
            <span
              key={severity}
              aria-hidden
              className={SEVERITY_BAR[severity]}
              style={{ width: `${(bySeverity[severity] / total) * 100}%` }}
            />
          ))}
        </div>
      )}
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        {SEVERITIES.map((severity) => (
          <div key={severity}>
            <dt className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase">
              {SEVERITY_LABEL[severity]}
            </dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums">{bySeverity[severity]}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
