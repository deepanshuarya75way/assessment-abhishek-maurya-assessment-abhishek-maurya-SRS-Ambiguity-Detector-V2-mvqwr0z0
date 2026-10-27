/**
 * Report-view derivations (Stage 09): PRESENTATIONAL aggregations over a
 * persisted `AnalysisResult` — counts, health labels, filter/sort. Scores,
 * severities, bands, and offsets always come from the backend untouched;
 * this module only groups, counts, labels, and orders for display. No
 * fetching, no state, no JSX — unit-tested in `reporting.test.ts`.
 */

import type { RequirementSeverity, SegmentedRequirement } from "../types/analysis";

/** Visible requirement health — derived from persisted score/severity only. */
export type RequirementHealth =
  "healthy" | "needs-attention" | "high-ambiguity" | "critical" | "not-scored";

export interface HealthInfo {
  state: RequirementHealth;
  label: string;
}

export function requirementHealth(requirement: SegmentedRequirement): HealthInfo {
  if (requirement.score === null) return { state: "not-scored", label: "Not scored" };
  if (requirement.issues.length === 0) return { state: "healthy", label: "Healthy" };
  switch (requirement.severity) {
    case "critical":
      return { state: "critical", label: "Critical" };
    case "high":
      return { state: "high-ambiguity", label: "High ambiguity" };
    default:
      return { state: "needs-attention", label: "Needs attention" };
  }
}

export interface CategoryCount {
  category: string;
  count: number;
}

/**
 * Issue counts per category, most-frequent first (ties keep first-seen
 * order — the sort is stable). Pure count of the persisted nested issues.
 */
export function countByCategory(requirements: SegmentedRequirement[]): CategoryCount[] {
  const counts = new Map<string, number>();
  for (const requirement of requirements) {
    for (const issue of requirement.issues) {
      counts.set(issue.category, (counts.get(issue.category) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count);
}

/** Issue counts per severity — all four keys, zeros included (honest distribution). */
export function countBySeverity(
  requirements: SegmentedRequirement[],
): Record<RequirementSeverity, number> {
  const counts: Record<RequirementSeverity, number> = { low: 0, medium: 0, high: 0, critical: 0 };
  for (const requirement of requirements) {
    for (const issue of requirement.issues) {
      counts[issue.severity] += 1;
    }
  }
  return counts;
}

export type StatusFilter = "all" | "with-issues" | "clean";
export type SeverityFilter = "all" | RequirementSeverity;
export type SortMode = "original" | "lowest-score" | "most-issues";

export interface ReportFilterState {
  query: string;
  status: StatusFilter;
  severity: SeverityFilter;
  sort: SortMode;
}

export const DEFAULT_FILTERS: ReportFilterState = {
  query: "",
  status: "all",
  severity: "all",
  sort: "original",
};

/**
 * Filter rows by status + requirement severity + free-text query (matched
 * against requirement text and identifier, case-insensitive). Operates on
 * the RENDERED nested issues — what the list can actually show.
 */
export function filterRequirements(
  requirements: SegmentedRequirement[],
  filters: Pick<ReportFilterState, "query" | "status" | "severity">,
): SegmentedRequirement[] {
  const query = filters.query.trim().toLowerCase();
  return requirements.filter((requirement) => {
    if (filters.status === "with-issues" && requirement.issues.length === 0) return false;
    if (filters.status === "clean" && requirement.issues.length > 0) return false;
    if (filters.severity !== "all" && requirement.severity !== filters.severity) return false;
    if (query === "") return true;
    return (
      requirement.text.toLowerCase().includes(query) ||
      (requirement.identifier ?? "").toLowerCase().includes(query)
    );
  });
}

/**
 * Order rows. `original` is an EXPLICIT position sort (never input-order
 * luck); the other modes break ties by position so the SRS order still
 * shows through. Unscored rows sink to the bottom of score sorts.
 */
export function sortRequirements(
  requirements: SegmentedRequirement[],
  sort: SortMode,
): SegmentedRequirement[] {
  const rows = [...requirements];
  switch (sort) {
    case "lowest-score":
      rows.sort((a, b) => (a.score ?? 101) - (b.score ?? 101) || a.position - b.position);
      break;
    case "most-issues":
      rows.sort((a, b) => b.issues.length - a.issues.length || a.position - b.position);
      break;
    case "original":
      rows.sort((a, b) => a.position - b.position);
      break;
  }
  return rows;
}
