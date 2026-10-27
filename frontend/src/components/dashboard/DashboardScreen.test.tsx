// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisSummary } from "@/types/analysis";
import type { DashboardRange, DashboardSnapshot } from "@/types/dashboard";
import { AuthProvider } from "@/components/auth/AuthProvider";

import { DashboardScreen } from "./DashboardScreen";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

function summary(overrides: Partial<AnalysisSummary> = {}): AnalysisSummary {
  return {
    id: "analysis-1",
    title: "Login SRS",
    status: "analyzed",
    source_type: "text",
    document: null,
    source_excerpt: "FR-001: hi",
    score: 78,
    band: "moderate",
    requirements_count: 3,
    issues_count: 5,
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
    ...overrides,
  };
}

function snapshot(overrides: Partial<DashboardSnapshot> = {}): DashboardSnapshot {
  return {
    range: "30d",
    stats: {
      analyses_total: 3,
      analyses_scored: 3,
      requirements_total: 9,
      issues_total: 7,
      avg_score: 76.5,
      latest: {
        id: "latest-1",
        title: "Latest run",
        score: 82,
        band: "low",
        created_at: "2026-09-24T00:00:00Z",
      },
      high_risk_count: 1,
      improved_count: 2,
      top_category: { category: "Vague quantifiers", count: 4 },
    },
    bands: [
      { band: "low", count: 1 },
      { band: "moderate", count: 1 },
      { band: "high", count: 1 },
      { band: "very_high", count: 0 },
    ],
    sources: [
      { source_type: "text", count: 2 },
      { source_type: "document", count: 1 },
    ],
    categories: [
      { category: "Vague quantifiers", count: 4 },
      { category: "Passive voice / unclear actor", count: 3 },
    ],
    severity: [
      { severity: "low", count: 1 },
      { severity: "medium", count: 4 },
      { severity: "high", count: 2 },
      { severity: "critical", count: 0 },
    ],
    trend: [
      { bucket: "2026-09-22", avg_score: null, analyses: 0, requirements: 0 },
      { bucket: "2026-09-23", avg_score: 70, analyses: 2, requirements: 6 },
      { bucket: "2026-09-24", avg_score: 82, analyses: 1, requirements: 3 },
    ],
    recent: [summary(), summary({ id: "analysis-2", title: "Second run" })],
    ...overrides,
  };
}

function emptySnapshot(range: DashboardRange = "30d"): DashboardSnapshot {
  return {
    range,
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

function stubFetch(handler: (url: string) => Response | Promise<Response>): { urls: string[] } {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh"))
        return errorResponse("unauthenticated", "Session expired.", 401);
      return handler(url);
    }),
  );
  return { urls };
}

function dashboardUrls(urls: string[]): string[] {
  return urls.filter((url) => url.includes("/dashboard?"));
}

function renderScreen() {
  render(
    <AuthProvider>
      <DashboardScreen />
    </AuthProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DashboardScreen", () => {
  it("renders the snapshot verbatim with a clean heading outline", async () => {
    let release!: (response: Response) => void;
    stubFetch(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    renderScreen();
    expect(await screen.findByLabelText("Loading dashboard")).toBeDefined();
    release(jsonResponse(snapshot()));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeDefined();
    for (const name of [
      "Ambiguity score over time",
      "Latest run",
      "Score bands",
      "Issue categories",
      "Issue severity",
      "Recent analyses",
    ]) {
      expect(screen.getByRole("heading", { name })).toBeDefined();
    }

    // Stats strip: persisted aggregates, zero recalculation.
    expect(screen.getByText("Analyses")).toBeDefined();
    expect(screen.getByText("76.5")).toBeDefined();
    expect(screen.getByText("3 runs scored")).toBeDefined();
    expect(screen.getByText("2 runs from pasted text · 1 run from file uploads")).toBeDefined();

    // Latest run: gauge + report link.
    expect(screen.getByRole("img", { name: /Ambiguity score 82 out of 100/ })).toBeDefined();
    expect(screen.getByRole("link", { name: "Latest run" })).toHaveProperty(
      "href",
      expect.stringContaining("/analysis/latest-1"),
    );

    // Distributions carry persisted vocabulary + honest captions.
    expect(screen.getAllByText("Low ambiguity")).toHaveLength(2);
    expect(screen.getByText("1 run in high bands.")).toBeDefined();
    expect(screen.getByText(/most frequent: Vague quantifiers \(4 of 7\)/)).toBeDefined();
    expect(
      screen.getByRole("img", { name: "Severity mix: 1 low, 4 medium, 2 high" }),
    ).toBeDefined();

    // Recent runs link out; footnote stays humble.
    expect(screen.getByRole("link", { name: "Login SRS" })).toHaveProperty(
      "href",
      expect.stringContaining("/analysis/analysis-1"),
    );
    expect(screen.getByText(/ranking aids for\s+triage/)).toBeDefined();
  });

  it("stacks stats on mobile and keeps the trend table from overflowing", async () => {
    stubFetch(() => jsonResponse(snapshot()));
    const { container } = render(
      <AuthProvider>
        <DashboardScreen />
      </AuthProvider>,
    );
    expect(await screen.findByText("Ambiguity score over time")).toBeDefined();
    const stats = screen.getByText("Analyses").closest("dl");
    expect(stats?.className).toMatch(/grid-cols-2/);
    expect(stats?.className).toMatch(/lg:grid-cols-4/);
    expect(container.querySelector(".overflow-x-auto")).not.toBeNull();
  });

  it("empty accounts get a first-use panel, not zero charts", async () => {
    stubFetch(() => jsonResponse(emptySnapshot()));
    renderScreen();
    expect(await screen.findByRole("heading", { name: "No analyses yet" })).toBeDefined();
    expect(screen.getByRole("link", { name: /Analyze requirements/ })).toHaveProperty(
      "href",
      expect.stringContaining("/analyzer"),
    );
    expect(screen.queryByText("Ambiguity score over time")).toBeNull();
    expect(screen.queryByText("Average score")).toBeNull();
  });

  it("maps API failures to honest copy with a working retry", async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) return errorResponse("internal_error", "Database down.", 500);
      return jsonResponse(snapshot());
    });
    renderScreen();
    expect(
      await screen.findByRole("heading", { name: "Couldn't load your dashboard" }),
    ).toBeDefined();
    expect(screen.getByText("Something went wrong. Please try again.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Ambiguity score over time")).toBeDefined();
  });

  it("rejects wrong-shape payloads instead of rendering garbage", async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) return jsonResponse({ range: "30d", stats: {}, trend: "nope" });
      return jsonResponse(snapshot());
    });
    renderScreen();
    expect(await screen.findByText("The service returned an unexpected response.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Ambiguity score over time")).toBeDefined();
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

  it("switches ranges through the API and dims the stale trend", async () => {
    const user = userEvent.setup();
    let release!: (response: Response) => void;
    let calls = 0;
    const { urls } = stubFetch(() => {
      calls += 1;
      if (calls === 1) return jsonResponse(snapshot());
      return new Promise<Response>((resolve) => {
        release = resolve;
      });
    });
    renderScreen();
    expect(await screen.findByText("Ambiguity score over time")).toBeDefined();

    await user.click(screen.getByRole("button", { name: "Last 12 weeks" }));
    await waitFor(() => expect(dashboardUrls(urls).at(-1)).toContain("range=12w"));
    const section = screen
      .getByRole("heading", { name: "Ambiguity score over time" })
      .closest("section");
    expect(section?.getAttribute("aria-busy")).toBe("true");

    release(jsonResponse(snapshot({ range: "12w" })));
    await waitFor(() => expect(section?.getAttribute("aria-busy")).toBe("false"));
    expect(screen.getByRole("button", { name: "Last 12 weeks" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("reads unscored runs and zero issues honestly", async () => {
    stubFetch(() =>
      jsonResponse(
        snapshot({
          stats: {
            analyses_total: 2,
            analyses_scored: 0,
            requirements_total: 4,
            issues_total: 0,
            avg_score: null,
            latest: {
              id: "failed-1",
              title: "Broken run",
              score: null,
              band: null,
              created_at: "2026-09-24T00:00:00Z",
            },
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
          categories: [],
          severity: [
            { severity: "low", count: 0 },
            { severity: "medium", count: 0 },
            { severity: "high", count: 0 },
            { severity: "critical", count: 0 },
          ],
          trend: [{ bucket: "2026-09-24", avg_score: null, analyses: 2, requirements: 4 }],
          recent: [
            summary({
              id: "failed-1",
              title: "Broken run",
              status: "failed",
              score: null,
              band: null,
            }),
          ],
        }),
      ),
    );
    renderScreen();
    expect(await screen.findByText("Ambiguity score over time")).toBeDefined();
    expect(screen.getByText("0 runs scored")).toBeDefined();
    expect(screen.getByText("no scored runs yet")).toBeDefined();
    expect(screen.getByText("Not scored")).toBeDefined();
    expect(screen.getByText("No runs in high bands.")).toBeDefined();
    expect(screen.getByText(/No issue categories yet/)).toBeDefined();
    expect(screen.getByText(/No issues found across your analyses yet/)).toBeDefined();
    expect(screen.getByText("Failed")).toBeDefined();
    expect(screen.queryByText("76.5")).toBeNull();
  });
});
