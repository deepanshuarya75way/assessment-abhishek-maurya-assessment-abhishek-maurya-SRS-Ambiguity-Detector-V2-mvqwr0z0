/**
 * Analysis domain types — mirrored from the project contract
 * (Stage 07: engine-scored `analyzed` rows; pre-Stage-07 `segmented` rows
 * still read back with null scores). Backend: `app/schemas/analysis.py`.
 * Same names, same optionality.
 */

/** Pipeline stage. POST returns `analyzed`; `segmented` is legacy; `failed` reserved (nothing writes it yet — the report renders a failure state if one ever reads back). */
export type AnalysisStatus = "segmented" | "analyzed" | "failed";

/** How one requirement was detected (segmentation evidence, not a score). */
export type SegmentationStrategy =
  "requirement_id" | "decimal" | "numbered" | "bullet" | "paragraph";

export interface SegmentationMeta {
  strategy: SegmentationStrategy;
  confidence: number;
  start_offset: number;
  end_offset: number;
  line_start: number;
  line_end: number;
}

export type RequirementSeverity = "low" | "medium" | "high" | "critical";

/** One detector finding — nested under its requirement (no parent id). */
export interface AnalysisIssue {
  id: string;
  detector_id: string;
  category: string;
  severity: RequirementSeverity;
  phrase: string;
  start_offset: number;
  end_offset: number;
  reason: string;
  recommendation: string;
  ai_explanation: string | null;
}

/** One scored requirement — `severity` is null when no issues fired. */
export interface SegmentedRequirement {
  id: string;
  position: number;
  identifier: string | null;
  section: string | null;
  text: string;
  score: number | null;
  severity: RequirementSeverity | null;
  issues_count: number;
  suggested_rewrite: string | null;
  suggestion_source: "rule" | "ai" | null;
  segmentation: SegmentationMeta;
  issues: AnalysisIssue[];
}

export type AnalysisBand = "low" | "moderate" | "high" | "very_high";

export interface ScoreDeduction {
  issue_id: string;
  severity: RequirementSeverity;
  points: number;
}

/** Transparent breakdown: base + per-issue deductions + severity counts. */
export interface ScoreBreakdown {
  base: number;
  deductions: ScoreDeduction[];
  counts: Record<RequirementSeverity, number>;
}

/** Supplementary dimensions (each 100 − mapped deductions, clamped). */
export interface HealthDimensions {
  clarity: number;
  specificity: number;
  measurability: number;
  completeness: number;
}

/**
 * Analysis detail (POST result + GET by id). Issues live nested per
 * requirement; there is no top-level `issues` and no `source_excerpt`
 * (summary-only) in the detail.
 */
/** Source-document display pointer (`document` analyses only, else null). */
export interface AnalysisDocumentRef {
  filename: string;
  file_type: "pdf" | "docx" | "txt";
}

/** AI enhancement outcome (Stage 14): `ok` = overview (+ rewrites) generated;
 * `failed` = attempted, user-safe `ai_error` explains; `skipped` = not
 * requested; `unconfigured` = requested but no usable provider. */
export type AiStatus = "ok" | "failed" | "skipped" | "unconfigured";

/** POST /analysis/{id}/retry-ai — the four restamped AI fields only (Stage 17).
 * Clients re-read the full detail (fresh rewrites included) after a retry. */
export interface AiRetryResult {
  ai_status: AiStatus;
  ai_overview: string | null;
  ai_provider: string | null;
  ai_error: string | null;
}

export interface AnalysisResult {
  id: string;
  title: string;
  status: AnalysisStatus;
  source_type: "text" | "document";
  document: AnalysisDocumentRef | null;
  score: number | null;
  band: AnalysisBand | null;
  score_breakdown: ScoreBreakdown;
  requirements_count: number;
  issues_count: number;
  health: HealthDimensions | null;
  ai_overview: string | null;
  ai_provider: string | null;
  ai_status: AiStatus;
  ai_error: string | null;
  requirements: SegmentedRequirement[];
  created_at: string;
  updated_at: string;
}

/** History-list row: detail minus `requirements`, plus `source_excerpt`.
 * Stage 10: carries the `document` display pointer (like the detail). */
export interface AnalysisSummary {
  id: string;
  title: string;
  status: AnalysisStatus;
  source_type: "text" | "document";
  document: AnalysisDocumentRef | null;
  source_excerpt: string | null;
  score: number | null;
  band: AnalysisBand | null;
  requirements_count: number;
  issues_count: number;
  created_at: string;
  updated_at: string;
}

export type AnalysisSort = "created_at" | "-created_at" | "score" | "-score";

export interface ListAnalysesParams {
  page?: number;
  page_size?: number;
  sort?: AnalysisSort;
  band?: AnalysisBand;
  source_type?: "text" | "document";
  /** History search (Stage 10): title + document filename substring, ≤200 chars. */
  q?: string;
}

export interface CreateAnalysisInput {
  title: string;
  text: string;
  /** Opt into the post-commit AI step (Stage 14): overview + per-requirement
   * rewrites via the user's own provider; false = deterministic-only. */
  aiEnhance: boolean;
}
