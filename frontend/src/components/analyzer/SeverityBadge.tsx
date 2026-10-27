import type { RequirementSeverity } from "@/types/analysis";

const SEVERITY_STYLES: Record<RequirementSeverity, string> = {
  low: "text-sev-low",
  medium: "text-sev-medium",
  high: "text-sev-high",
  critical: "text-sev-critical",
};

const SEVERITY_LABELS: Record<RequirementSeverity, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

/**
 * Severity indicator: dot + text label (never color alone —
 * the label carries the meaning for color-blind + screen-reader users).
 */
export function SeverityBadge({ severity }: { severity: RequirementSeverity }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 font-mono text-xs font-medium ${SEVERITY_STYLES[severity]}`}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {SEVERITY_LABELS[severity]}
    </span>
  );
}
