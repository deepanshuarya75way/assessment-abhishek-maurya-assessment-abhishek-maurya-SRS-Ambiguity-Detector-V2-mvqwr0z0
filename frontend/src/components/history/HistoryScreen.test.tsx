// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisSummary } from "@/types/analysis";
import type { Collection } from "@/lib/api";
import { AuthProvider } from "@/components/auth/AuthProvider";

import { HistoryScreen } from "./HistoryScreen";

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

function collection(
  items: AnalysisSummary[],
  total: number,
  page = 1,
): Collection<AnalysisSummary> {
  return { items, page, page_size: 20, total };
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

function stubFetch(
  handler: (url: string, init?: { method?: string }) => Response | Promise<Response>,
) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: { method?: string }) => {
      const url = String(input);
      urls.push(url);
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh"))
        return errorResponse("unauthenticated", "Session expired.", 401);
      return handler(url, init);
    }),
  );
  return urls;
}

function listUrls(urls: string[]): string[] {
  return urls.filter((url) => /\/analysis(\?|$)/.test(url) && !/\/analysis\//.test(url));
}

function renderScreen() {
  render(
    <AuthProvider>
      <HistoryScreen />
    </AuthProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("HistoryScreen", () => {
  it("loads the first page with header, rows, count, and navigation links", async () => {
    let release!: (response: Response) => void;
    stubFetch(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    renderScreen();
    expect(await screen.findByLabelText("Loading history")).toBeDefined();
    release(
      jsonResponse(
        collection(
          [
            summary(),
            summary({
              id: "analysis-2",
              title: "Contract review",
              status: "failed",
              source_type: "document",
              document: { filename: "contract.pdf", file_type: "pdf" },
              score: null,
              band: null,
              requirements_count: 0,
              issues_count: 0,
            }),
          ],
          2,
        ),
      ),
    );
    expect(await screen.findByText("Showing 2 of 2 analyses")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Analysis history" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Analyzer" })).toHaveProperty(
      "href",
      expect.stringContaining("/analyzer"),
    );
    expect(screen.getByText("Login SRS")).toBeDefined();
    expect(screen.getByText("Failed")).toBeDefined();
    expect(screen.getByRole("link", { name: "Open Login SRS" })).toHaveProperty(
      "href",
      expect.stringContaining("/analysis/analysis-1"),
    );
    expect(screen.queryByRole("navigation", { name: "History pages" })).toBeNull();
  });

  it("empty accounts get a no-analyses panel with an analyzer CTA (no toolbar)", async () => {
    stubFetch(() => jsonResponse(collection([], 0)));
    renderScreen();
    expect(await screen.findByRole("heading", { name: "No analyses yet" })).toBeDefined();
    expect(screen.getByRole("link", { name: /Analyze requirements/ })).toHaveProperty(
      "href",
      expect.stringContaining("/analyzer"),
    );
    expect(screen.queryByLabelText("Search")).toBeNull();
  });

  it("filtered empties stay distinct with a working clear action", async () => {
    const user = userEvent.setup();
    stubFetch((url) =>
      url.includes("band=high")
        ? jsonResponse(collection([], 0))
        : jsonResponse(collection([summary()], 1)),
    );
    renderScreen();
    expect(await screen.findByText("Login SRS")).toBeDefined();
    await user.selectOptions(screen.getByLabelText("Band"), "high");
    expect(await screen.findByRole("heading", { name: "No matching results" })).toBeDefined();
    expect(screen.getByLabelText("Search")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(await screen.findByText("Login SRS")).toBeDefined();
    expect((screen.getByLabelText("Band") as HTMLSelectElement).value).toBe("all");
  });

  it("maps API failures to honest copy with a working retry", async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) return errorResponse("internal_error", "Database down.", 500);
      return jsonResponse(collection([summary()], 1));
    });
    renderScreen();
    expect(
      await screen.findByRole("heading", { name: "Couldn't load your history" }),
    ).toBeDefined();
    expect(screen.getByText("Something went wrong. Please try again.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Login SRS")).toBeDefined();
  });

  it("rejects wrong-shape payloads instead of rendering garbage", async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) return jsonResponse({ items: "nope", total: 1 });
      return jsonResponse(collection([summary()], 1));
    });
    renderScreen();
    expect(await screen.findByText("The service returned an unexpected response.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Login SRS")).toBeDefined();
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

  it("sends band, source, and sort changes to the API and resets to page 1", async () => {
    const user = userEvent.setup();
    const urls = stubFetch(() => jsonResponse(collection([summary()], 1)));
    renderScreen();
    expect(await screen.findByText("Login SRS")).toBeDefined();

    await user.selectOptions(screen.getByLabelText("Band"), "high");
    await waitFor(() => expect(listUrls(urls).at(-1)).toContain("band=high"));
    expect(listUrls(urls).at(-1)).toContain("page=1");

    await user.selectOptions(screen.getByLabelText("Source"), "document");
    await waitFor(() => expect(listUrls(urls).at(-1)).toContain("source_type=document"));

    await user.selectOptions(screen.getByLabelText("Sort"), "-score");
    await waitFor(() => expect(listUrls(urls).at(-1)).toContain("sort=-score"));
    expect(listUrls(urls).at(-1)).not.toContain("q=");
  });

  it("debounces search keystrokes into one backend query", async () => {
    const user = userEvent.setup();
    const urls = stubFetch((url) =>
      url.includes("q=acme")
        ? jsonResponse(collection([summary({ title: "Acme SRS" })], 1))
        : jsonResponse(collection([summary()], 1)),
    );
    renderScreen();
    expect(await screen.findByText("Login SRS")).toBeDefined();
    const before = listUrls(urls).length;

    await user.type(screen.getByLabelText("Search"), "acme");
    expect(screen.getByText("Searching…")).toBeDefined();
    expect(listUrls(urls)).toHaveLength(before);
    expect(await screen.findByText("Acme SRS")).toBeDefined();
    const last = listUrls(urls).at(-1) ?? "";
    expect(last).toContain("q=acme");
    expect(last).toContain("page=1");
  });

  it("pages forward and back with honest disabled states", async () => {
    const user = userEvent.setup();
    const pageOf = (page: number) =>
      jsonResponse({
        items: [summary({ id: `analysis-${page}`, title: `SRS ${page}` })],
        page,
        page_size: 1,
        total: 3,
      });
    stubFetch((url) => pageOf(new URL(url).searchParams.get("page") === "2" ? 2 : 1));
    renderScreen();
    expect(await screen.findByText("SRS 1")).toBeDefined();
    expect(screen.getByText("Page 1 of 3")).toBeDefined();
    expect(screen.getByRole("button", { name: "Previous" })).toHaveProperty("disabled", true);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("SRS 2")).toBeDefined();
    expect(screen.getByText("Page 2 of 3")).toBeDefined();
    expect(screen.getByRole("button", { name: "Previous" })).toHaveProperty("disabled", false);

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("SRS 1")).toBeDefined();
  });

  it("dims stale pages as busy while the next page loads", async () => {
    const user = userEvent.setup();
    let release!: (response: Response) => void;
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) return jsonResponse(collection([summary()], 1));
      return new Promise<Response>((resolve) => {
        release = resolve;
      });
    });
    renderScreen();
    expect(await screen.findByText("Login SRS")).toBeDefined();
    await user.selectOptions(screen.getByLabelText("Band"), "low");
    const busy = screen.getByRole("table").closest("[aria-busy]");
    expect(busy?.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Login SRS")).toBeDefined();
    release(jsonResponse(collection([summary({ title: "Low SRS" })], 1)));
    expect(await screen.findByText("Low SRS")).toBeDefined();
    expect(screen.getByRole("table").closest("[aria-busy]")?.getAttribute("aria-busy")).toBe(
      "false",
    );
  });

  it("deletes a row through confirm and refetches without it", async () => {
    const user = userEvent.setup();
    let deleted = false;
    stubFetch((url, init) => {
      if (init?.method === "DELETE") {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      return deleted ? jsonResponse(collection([], 0)) : jsonResponse(collection([summary()], 1));
    });
    renderScreen();
    expect(await screen.findByText("Login SRS")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Delete Login SRS" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    expect(await screen.findByRole("heading", { name: "No analyses yet" })).toBeDefined();
  });

  it("clamps to the previous page when a delete empties the current one", async () => {
    const user = userEvent.setup();
    let deleted = false;
    stubFetch((url, init) => {
      if (init?.method === "DELETE") {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      const page = new URL(url).searchParams.get("page") ?? "1";
      if (page === "2") {
        return deleted
          ? jsonResponse({ items: [], page: 2, page_size: 1, total: 1 })
          : jsonResponse({
              items: [summary({ id: "analysis-2", title: "SRS 2" })],
              page: 2,
              page_size: 1,
              total: 2,
            });
      }
      return jsonResponse({
        items: [summary({ id: "analysis-1", title: "SRS 1" })],
        page: 1,
        page_size: 1,
        total: deleted ? 1 : 2,
      });
    });
    renderScreen();
    expect(await screen.findByText("SRS 1")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("SRS 2")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Delete SRS 2" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    expect(await screen.findByText("SRS 1")).toBeDefined();
    expect(screen.queryByRole("navigation", { name: "History pages" })).toBeNull();
  });

  it("keeps the row and shows mapped copy when deletion fails", async () => {
    const user = userEvent.setup();
    stubFetch((_url, init) => {
      if (init?.method === "DELETE") return errorResponse("internal_error", "Database down.", 500);
      return jsonResponse(collection([summary()], 1));
    });
    renderScreen();
    expect(await screen.findByText("Login SRS")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Delete Login SRS" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    expect(await screen.findByRole("alert")).toBeDefined();
    expect(screen.getByText("Something went wrong. Please try again.")).toBeDefined();
    expect(
      within(screen.getByRole("table")).getByRole("link", { name: "Login SRS" }),
    ).toBeDefined();
  });
});
