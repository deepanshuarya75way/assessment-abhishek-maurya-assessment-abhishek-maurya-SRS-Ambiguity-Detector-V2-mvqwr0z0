// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisResult } from "@/types/analysis";
import { AuthProvider } from "@/components/auth/AuthProvider";

import { AnalysisReportScreen } from "./AnalysisReportScreen";

const route = vi.hoisted(() => ({ id: "analysis-1" as unknown }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => ({ id: route.id }),
}));

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(code: string, message: string, status: number): Response {
  return jsonResponse({ error: { code, message } }, status);
}

function userResponse(): Response {
  return jsonResponse({
    id: "user-1",
    email: "ada@example.com",
    display_name: "Ada",
    is_verified: true,
    is_active: true,
    created_at: "2026-09-24T00:00:00Z",
  });
}

function analysisResult(): AnalysisResult {
  return {
    id: "analysis-1",
    title: "Login SRS",
    status: "analyzed",
    source_type: "text",
    document: null,
    score: 85,
    band: "low",
    score_breakdown: {
      base: 100,
      deductions: [{ issue_id: "issue-1", severity: "high", points: 15 }],
      counts: { low: 0, medium: 0, high: 1, critical: 0 },
    },
    requirements_count: 2,
    issues_count: 1,
    health: { measurability: 90, specificity: 100, clarity: 100, completeness: 100 },
    ai_overview: null,
    ai_provider: null,
    ai_status: "skipped",
    ai_error: null,
    requirements: [
      {
        id: "req-1",
        position: 0,
        identifier: "FR-001",
        section: null,
        text: "The service should be fast.",
        score: 70,
        severity: "high",
        issues_count: 1,
        suggested_rewrite: null,
        suggestion_source: null,
        segmentation: {
          strategy: "requirement_id",
          confidence: 0.95,
          start_offset: 0,
          end_offset: 27,
          line_start: 1,
          line_end: 1,
        },
        issues: [
          {
            id: "issue-1",
            detector_id: "subjective-term",
            category: "Subjective term",
            severity: "high",
            phrase: "fast",
            start_offset: 22,
            end_offset: 26,
            reason: "“fast” means different response times to different reviewers.",
            recommendation: "State the response time in milliseconds.",
            ai_explanation: null,
          },
        ],
      },
      {
        id: "req-2",
        position: 1,
        identifier: "FR-002",
        section: null,
        text: "The system shall allow login.",
        score: 100,
        severity: null,
        issues_count: 0,
        suggested_rewrite: null,
        suggestion_source: null,
        segmentation: {
          strategy: "requirement_id",
          confidence: 0.95,
          start_offset: 28,
          end_offset: 57,
          line_start: 2,
          line_end: 2,
        },
        issues: [],
      },
    ],
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
  };
}

function stubFetch(handler: (url: string) => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh"))
        return errorResponse("unauthenticated", "Session expired.", 401);
      return handler(url);
    }),
  );
}

function renderScreen() {
  render(
    <AuthProvider>
      <AnalysisReportScreen />
    </AuthProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  route.id = "analysis-1";
});

describe("AnalysisReportScreen", () => {
  it("loads one owned analysis and renders the saved report with back + delete", async () => {
    let seenUrl = "";
    stubFetch((url) => {
      seenUrl = url;
      return jsonResponse(analysisResult());
    });
    renderScreen();

    expect(await screen.findByText("Saved analysis · 2 requirements · 1 issue")).toBeDefined();
    expect(seenUrl).toContain("/analysis/analysis-1");
    expect(screen.getByRole("heading", { name: "Login SRS" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Back to Analyzer" })).toHaveProperty(
      "href",
      expect.stringContaining("/analyzer"),
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDefined();
  });

  it("maps missing + foreign + malformed ids to one honest not-found panel", async () => {
    stubFetch(() => errorResponse("not_found", "No analysis with id x.", 404));
    renderScreen();
    expect(await screen.findByRole("heading", { name: "Analysis not found" })).toBeDefined();
    expect(screen.getByText(/private to the account/)).toBeDefined();
    expect(screen.queryByText(/Saved analysis/)).toBeNull();
  });

  it("maps malformed ids (validation error) to the same not-found panel", async () => {
    stubFetch(() => errorResponse("validation_error", "Invalid UUID.", 400));
    renderScreen();
    expect(await screen.findByRole("heading", { name: "Analysis not found" })).toBeDefined();
  });

  it("treats a missing route id as not-found without calling the API", async () => {
    route.id = undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/me")) return userResponse();
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderScreen();
    expect(await screen.findByRole("heading", { name: "Analysis not found" })).toBeDefined();
    expect(fetchMock.mock.calls.every(([input]) => String(input).includes("/auth/me"))).toBe(true);
  });

  it("offers a sign-in nudge when the session is exhausted", async () => {
    stubFetch(() => errorResponse("unauthenticated", "Session expired.", 401));
    renderScreen();
    expect(await screen.findByRole("heading", { name: "Session expired" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveProperty(
      "href",
      expect.stringContaining("/login"),
    );
  });

  it("retries transient failures without losing the route", async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) return errorResponse("internal_error", "Database down.", 500);
      return jsonResponse(analysisResult());
    });
    renderScreen();
    expect(
      await screen.findByRole("heading", { name: "Couldn't load this analysis" }),
    ).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Saved analysis · 2 requirements · 1 issue")).toBeDefined();
    expect(calls).toBe(2);
  });

  it("AI retry posts, then silently re-reads into the ok state (Stage 17)", async () => {
    const user = userEvent.setup();
    const failed = { ...analysisResult(), ai_status: "failed", ai_error: "Provider timed out." };
    const recovered = {
      ...analysisResult(),
      ai_status: "ok",
      ai_overview: "Fresh overview.",
      ai_provider: "groq",
      ai_error: null,
    };
    let gets = 0;
    let posts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/auth/me")) return userResponse();
        if (url.includes("/auth/refresh"))
          return errorResponse("unauthenticated", "Session expired.", 401);
        if (url.includes("/retry-ai") && init?.method === "POST") {
          posts += 1;
          return jsonResponse({
            ai_status: "ok",
            ai_overview: "Fresh overview.",
            ai_provider: "groq",
            ai_error: null,
          });
        }
        gets += 1;
        return jsonResponse(gets === 1 ? failed : recovered);
      }),
    );
    renderScreen();
    expect(await screen.findByRole("heading", { name: "AI enhancement failed" })).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    // Silent refresh: no skeleton flash — the ok block swaps straight in.
    expect(await screen.findByRole("heading", { name: "AI overview" })).toBeDefined();
    expect(screen.getByText("Fresh overview.")).toBeDefined();
    expect(posts).toBe(1);
    expect(gets).toBe(2);
  });
});
