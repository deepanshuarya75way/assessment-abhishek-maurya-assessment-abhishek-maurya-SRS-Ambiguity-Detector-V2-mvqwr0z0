/**
 * Dashboard snapshot types — mirror the project contract exactly.
 * Every value is a server aggregate over persisted analyses; the UI never
 * recomputes scores, bands, or severities from raw data.
 */

import type { AnalysisBand, AnalysisSummary, RequirementSeverity } from "./analysis";

/** Trend window: 30 trailing UTC days, or 12 trailing Monday-start UTC weeks. */
export type DashboardRange = "30d" | "12w";

export interface DashboardLatest {
  id: string;
  title: string;
  score: number | null;
  band: AnalysisBand | null;
  created_at: string;
}

export interface DashboardTopCategory {
  category: string;
  count: number;
}

export interface DashboardStats {
  analyses_total: number;
  analyses_scored: number;
  requirements_total: number;
  issues_total: number;
  /** Mean over SCORED analyses only (half-up, 1 decimal); null when none. */
  avg_score: number | null;
  /** Newest run overall — score/band null when it never scored. */
  latest: DashboardLatest | null;
  /** Scored runs with a persisted high/very_high band. */
  high_risk_count: number;
  /** Scored runs strictly above the preceding scored run (neutral count). */
  improved_count: number;
  top_category: DashboardTopCategory | null;
}

export interface DashboardBandCount {
  band: AnalysisBand;
  count: number;
}

export interface DashboardSourceCount {
  source_type: "text" | "document";
  count: number;
}

export interface DashboardCategoryCount {
  category: string;
  count: number;
}

export interface DashboardSeverityCount {
  severity: RequirementSeverity;
  count: number;
}

export interface DashboardTrendBucket {
  /** UTC calendar date (`YYYY-MM-DD`): the day, or the week's Monday. */
  bucket: string;
  /** Mean over scored runs in the bucket; null when the bucket holds none. */
  avg_score: number | null;
  /** Every run in the bucket, scored or not. */
  analyses: number;
  requirements: number;
}

export interface DashboardSnapshot {
  range: DashboardRange;
  stats: DashboardStats;
  /** Always all four bands (zeros included), low → very_high. */
  bands: DashboardBandCount[];
  /** Always both source types (zeros included). */
  sources: DashboardSourceCount[];
  /** Non-zero categories only, most-frequent first. */
  categories: DashboardCategoryCount[];
  /** Always all four severities (zeros included). */
  severity: DashboardSeverityCount[];
  /** Zero-filled trailing window, oldest first. */
  trend: DashboardTrendBucket[];
  /** Up to 5 newest summaries. */
  recent: AnalysisSummary[];
}
