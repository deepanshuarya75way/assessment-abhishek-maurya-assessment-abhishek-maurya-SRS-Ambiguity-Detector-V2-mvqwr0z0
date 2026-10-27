import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardSnapshot } from "../types/dashboard";
import { ApiRequestError } from "./api";
import { getDashboard } from "./dashboard";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptySnapshot(): DashboardSnapshot {
  return {
    range: "30d",
    stats: {
      analyses_total: 0,
      analyses_scored: 0,
      requirements_total: 0,
      issues_total: 0,
      avg_score: null,
      latest: null,
      high_risk_count: 0,
      improved_count: 0,
      top_category: null,
    },
    bands: [
      { band: "low", count: 0 },
      { band: "moderate", count: 0 },
      { band: "high", count: 0 },
      { band: "very_high", count: 0 },
    ],
    sources: [
      { source_type: "text", count: 0 },
      { source_type: "document", count: 0 },
    ],
    categories: [],
    severity: [
      { severity: "low", count: 0 },
      { severity: "medium", count: 0 },
      { severity: "high", count: 0 },
      { severity: "critical", count: 0 },
    ],
    trend: [],
    recent: [],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("getDashboard", () => {
  it("requests the documented range and returns the snapshot verbatim", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        urls.push(String(input));
        return jsonResponse(emptySnapshot());
      }),
    );
    const snapshot = await getDashboard("12w");
    expect(urls).toEqual([expect.stringContaining("/dashboard?range=12w")]);
    expect(snapshot).toEqual(emptySnapshot());
  });

  it("propagates the backend error code for the UI to switch on", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ error: { code: "internal_error", message: "db down" } }, 500),
      ),
    );
    const err = await getDashboard("30d").catch((error: unknown) => error);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as ApiRequestError).code).toBe("internal_error");
  });
});
