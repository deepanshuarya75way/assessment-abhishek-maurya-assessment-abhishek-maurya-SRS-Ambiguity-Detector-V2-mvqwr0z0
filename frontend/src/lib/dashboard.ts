/**
 * Dashboard API layer — the ONLY module that talks to `/dashboard`. Built
 * exclusively on the canonical client (`lib/api.ts`): cookies flow via
 * `credentials: "include"` and session tokens never touch JS.
 *
 * One aggregate snapshot per range (contract §4.5): the UI renders these
 * server aggregates verbatim and never recomputes statistics client-side.
 * Reads retry a stale session exactly like the analysis reads (safe: GET is
 * idempotent).
 */

import type { DashboardRange, DashboardSnapshot } from "../types/dashboard";

import { api } from "./api";
import { withSessionRetry } from "./auth";

/** Account-wide aggregate snapshot for the documented trailing window. */
export async function getDashboard(range: DashboardRange): Promise<DashboardSnapshot> {
  const search = new URLSearchParams({ range });
  return withSessionRetry(() => api<DashboardSnapshot>(`/dashboard?${search.toString()}`));
}
