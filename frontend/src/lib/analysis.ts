/**
 * Analysis API layer — the ONLY module that talks to `/analysis/*`. Built
 * exclusively on the canonical client (`lib/api.ts`): cookies flow via
 * `credentials: "include"` and session tokens never touch JS.
 *
 * Creation silent-refreshes a stale session exactly like `changePassword`: a
 * 401 means "not executed" (the guard rejects before the service runs), so the
 * single retry cannot double-create. Reads/deletes retry the same way (safe:
 * GETs are idempotent, DELETE targets one id).
 */

import type {
  AiRetryResult,
  AnalysisResult,
  AnalysisSummary,
  CreateAnalysisInput,
  ListAnalysesParams,
} from "../types/analysis";

import { api, type Collection } from "./api";
import { withSessionRetry } from "./auth";

/** Server limits mirrored for instant client feedback (server authoritative). */
export const ANALYZER_LIMITS = { maxChars: 200_000, maxTitle: 200 } as const;

/** Analyze pasted SRS text: segment + detect + score, persisted (Stage 07).
 * `aiEnhance` (Stage 14) opts the shared post-commit AI step in. */
export async function createAnalysis(input: CreateAnalysisInput): Promise<AnalysisResult> {
  return withSessionRetry(() =>
    api<AnalysisResult>("/analysis", {
      method: "POST",
      body: {
        title: input.title,
        text: input.text,
        options: { ai_enhance: input.aiEnhance },
      },
    }),
  );
}

/**
 * Re-run ONLY the AI enhancement step of a persisted analysis (Stage 17).
 * Retry-safe like creation: the guard rejects pre-execution on 401, and a
 * retry is idempotent-shaped (reset + rerun the same step — a doubled call
 * can only repeat the same outcome, never corrupt the deterministic record).
 */
export async function retryAi(id: string): Promise<AiRetryResult> {
  return withSessionRetry(() => api<AiRetryResult>(`/analysis/${id}/retry-ai`, { method: "POST" }));
}

/** Fetch one owned analysis with requirements + nested issues (404 if foreign). */
export async function getAnalysis(id: string): Promise<AnalysisResult> {
  return withSessionRetry(() => api<AnalysisResult>(`/analysis/${id}`));
}

/** Newest-first page of owned analyses (contract §3; server clamps paging). */
export async function listAnalyses(
  params: ListAnalysesParams = {},
): Promise<Collection<AnalysisSummary>> {
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.page_size !== undefined) search.set("page_size", String(params.page_size));
  if (params.sort !== undefined) search.set("sort", params.sort);
  if (params.band !== undefined) search.set("band", params.band);
  if (params.source_type !== undefined) search.set("source_type", params.source_type);
  if (params.q !== undefined) search.set("q", params.q);
  const query = search.size > 0 ? `?${search.toString()}` : "";
  return withSessionRetry(() => api<Collection<AnalysisSummary>>(`/analysis${query}`));
}

/** Delete one owned analysis (requirements + issues cascade). 204 → void. */
export async function deleteAnalysis(id: string): Promise<void> {
  return withSessionRetry(() => api<void>(`/analysis/${id}`, { method: "DELETE" }));
}
