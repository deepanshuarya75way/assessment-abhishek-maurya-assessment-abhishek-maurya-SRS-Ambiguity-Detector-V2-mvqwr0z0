import { afterEach, describe, expect, it, vi } from "vitest";

import type { AnalysisResult, AnalysisSummary, SegmentedRequirement } from "../types/analysis";
import type { Collection } from "./api";
import { ApiRequestError } from "./api";
import {
  ANALYZER_LIMITS,
  createAnalysis,
  deleteAnalysis,
  getAnalysis,
  listAnalyses,
  retryAi,
} from "./analysis";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `server ${code}` } }, status);
}

function requirement(overrides: Partial<SegmentedRequirement> = {}): SegmentedRequirement {
  return {
    id: "req-1",
    position: 0,
    identifier: "FR-001",
    section: "Functional Requirements",
    text: "The system shall allow login.",
    score: 100,
    severity: null,
    issues_count: 0,
    suggested_rewrite: null,
    suggestion_source: null,
    segmentation: {
      strategy: "requirement_id",
      confidence: 0.95,
      start_offset: 0,
      end_offset: 29,
      line_start: 1,
      line_end: 1,
    },
    issues: [],
    ...overrides,
  };
}

function analysisResult(): AnalysisResult {
  return {
    id: "analysis-1",
    title: "Login SRS",
    status: "analyzed",
    source_type: "text",
    document: null,
    score: 100,
    band: "low",
    score_breakdown: {
      base: 100,
      deductions: [],
      counts: { low: 0, medium: 0, high: 0, critical: 0 },
    },
    requirements_count: 1,
    issues_count: 0,
    health: { measurability: 100, specificity: 100, clarity: 100, completeness: 100 },
    ai_overview: null,
    ai_provider: null,
    ai_status: "skipped",
    ai_error: null,
    requirements: [requirement()],
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("analysis api layer", () => {
  it("posts title+text to /analysis and returns the parsed result", async () => {
    const inits: Array<RequestInit | undefined> = [];
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        urls.push(String(input));
        inits.push(init);
        return jsonResponse(analysisResult());
      }),
    );
    const result = await createAnalysis({
      title: "Login SRS",
      text: "FR-001: hi",
      aiEnhance: false,
    });
    expect(result).toEqual(analysisResult());
    expect(urls).toHaveLength(1);
    expect(urls[0]).toMatch(/\/analysis$/);
    expect(inits[0]?.method).toBe("POST");
    expect(JSON.parse(String(inits[0]?.body))).toEqual({
      title: "Login SRS",
      text: "FR-001: hi",
      options: { ai_enhance: false },
    });
  });

  it("sends options.ai_enhance true when the AI step is requested", async () => {
    const inits: Array<RequestInit | undefined> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        inits.push(init);
        return jsonResponse(analysisResult());
      }),
    );
    await createAnalysis({ title: "t", text: "FR-001: hi", aiEnhance: true });
    expect(JSON.parse(String(inits[0]?.body))).toEqual({
      title: "t",
      text: "FR-001: hi",
      options: { ai_enhance: true },
    });
  });

  it("sends a blank title as-is (the server applies the fallback)", async () => {
    const inits: Array<RequestInit | undefined> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        inits.push(init);
        return jsonResponse(analysisResult());
      }),
    );
    await createAnalysis({ title: "", text: "FR-001: hi", aiEnhance: false });
    expect(JSON.parse(String(inits[0]?.body))).toEqual({
      title: "",
      text: "FR-001: hi",
      options: { ai_enhance: false },
    });
  });

  it("silently refreshes once on 401, then retries the creation", async () => {
    const paths: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        paths.push(url);
        if (url.includes("/auth/refresh")) {
          return jsonResponse({ id: "u1", email: "ada@example.com", is_verified: true });
        }
        if (paths.filter((p) => p.endsWith("/analysis")).length === 1) {
          return envelope("unauthenticated", 401);
        }
        return jsonResponse(analysisResult());
      }),
    );
    const result = await createAnalysis({ title: "t", text: "FR-001: hi", aiEnhance: false });
    expect(result.id).toBe("analysis-1");
    expect(paths.filter((p) => p.endsWith("/analysis"))).toHaveLength(2);
    expect(paths.filter((p) => p.includes("/auth/refresh"))).toHaveLength(1);
  });

  it("rethows the ORIGINAL 401 when refresh fails (no loop, no masking)", async () => {
    const paths: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        paths.push(url);
        return url.includes("/auth/refresh")
          ? envelope("invalid_token", 400)
          : envelope("unauthenticated", 401);
      }),
    );
    const failure = await createAnalysis({
      title: "t",
      text: "FR-001: hi",
      aiEnhance: false,
    }).catch((err: unknown) => err);
    expect(failure).toBeInstanceOf(ApiRequestError);
    expect((failure as ApiRequestError).code).toBe("unauthenticated");
    expect(paths.filter((p) => p.endsWith("/analysis"))).toHaveLength(1);
  });

  it("does not retry non-401 failures", async () => {
    const fetchMock = vi.fn(async () => envelope("no_requirements_detected", 400));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      createAnalysis({ title: "t", text: "prose", aiEnhance: false }),
    ).rejects.toMatchObject({
      code: "no_requirements_detected",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("mirrors the server limits", () => {
    expect(ANALYZER_LIMITS).toEqual({ maxChars: 200_000, maxTitle: 200 });
  });
});

describe("getAnalysis", () => {
  it("fetches one owned analysis by id", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        urls.push(String(input));
        return jsonResponse(analysisResult());
      }),
    );
    const result = await getAnalysis("analysis-1");
    expect(result).toEqual(analysisResult());
    expect(urls).toHaveLength(1);
    expect(urls[0]).toMatch(/\/analysis\/analysis-1$/);
  });

  it("surfaces analysis_not_found for missing/foreign ids", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("analysis_not_found", 404)),
    );
    await expect(getAnalysis("someone-elses")).rejects.toMatchObject({
      code: "analysis_not_found",
    });
  });
});

describe("listAnalyses", () => {
  function pageResponse(): Collection<AnalysisSummary> {
    return {
      items: [
        {
          id: "analysis-1",
          title: "Login SRS",
          status: "analyzed",
          source_type: "text",
          document: null,
          source_excerpt: "FR-001: hi",
          score: 100,
          band: "low",
          requirements_count: 1,
          issues_count: 0,
          created_at: "2026-09-24T00:00:00Z",
          updated_at: "2026-09-24T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    };
  }

  it("requests the collection with no query when no params are given", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        urls.push(String(input));
        return jsonResponse(pageResponse());
      }),
    );
    const page = await listAnalyses();
    expect(page.total).toBe(1);
    expect(urls).toHaveLength(1);
    expect(urls[0]).toMatch(/\/analysis$/);
  });

  it("encodes paging, sort, and filters into the query string", async () => {
    let seen = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        seen = String(input);
        return jsonResponse(pageResponse());
      }),
    );
    await listAnalyses({
      page: 2,
      page_size: 5,
      sort: "-score",
      band: "high",
      source_type: "document",
      q: "acme contract",
    });
    const query = new URL(seen).searchParams;
    expect(query.get("page")).toBe("2");
    expect(query.get("page_size")).toBe("5");
    expect(query.get("sort")).toBe("-score");
    expect(query.get("band")).toBe("high");
    expect(query.get("source_type")).toBe("document");
    expect(query.get("q")).toBe("acme contract");
  });
});

describe("deleteAnalysis", () => {
  it("issues DELETE and resolves void on 204", async () => {
    const inits: Array<RequestInit | undefined> = [];
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        urls.push(String(input));
        inits.push(init);
        return new Response(null, { status: 204 });
      }),
    );
    await expect(deleteAnalysis("analysis-1")).resolves.toBeUndefined();
    expect(urls[0]).toMatch(/\/analysis\/analysis-1$/);
    expect(inits[0]?.method).toBe("DELETE");
  });

  it("surfaces analysis_not_found when the id is missing/foreign", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("analysis_not_found", 404)),
    );
    await expect(deleteAnalysis("someone-elses")).rejects.toMatchObject({
      code: "analysis_not_found",
    });
  });
});

describe("retryAi", () => {
  const RETRY_OK = {
    ai_status: "ok",
    ai_overview: "Fresh overview.",
    ai_provider: "groq",
    ai_error: null,
  };

  it("POSTs the retry path and returns the four restamped fields", async () => {
    let seenUrl = "";
    let seenMethod = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        seenUrl = String(input);
        seenMethod = init?.method ?? "GET";
        return jsonResponse(RETRY_OK);
      }),
    );
    await expect(retryAi("analysis-1")).resolves.toEqual(RETRY_OK);
    expect(seenUrl).toMatch(/\/analysis\/analysis-1\/retry-ai$/);
    expect(seenMethod).toBe("POST");
  });

  it("silently refreshes once on 401, then retries the POST", async () => {
    const posts: string[] = [];
    const refreshes: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/refresh")) {
          refreshes.push(url);
          return jsonResponse({ id: "u1", email: "ada@example.com", is_verified: true });
        }
        posts.push(url);
        return posts.length === 1 ? envelope("unauthenticated", 401) : jsonResponse(RETRY_OK);
      }),
    );
    await expect(retryAi("analysis-1")).resolves.toEqual(RETRY_OK);
    expect(posts).toHaveLength(2);
    expect(refreshes).toHaveLength(1);
  });

  it("surfaces analysis_not_found when the id is missing/foreign", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("analysis_not_found", 404)),
    );
    await expect(retryAi("someone-elses")).rejects.toMatchObject({
      code: "analysis_not_found",
    });
  });
});
