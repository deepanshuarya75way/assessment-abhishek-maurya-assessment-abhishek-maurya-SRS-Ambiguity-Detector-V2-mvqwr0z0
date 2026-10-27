// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisResult } from "@/types/analysis";
import { AuthProvider } from "@/components/auth/AuthProvider";

import { AnalyzerWorkspace } from "./AnalyzerWorkspace";

const nav = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: nav.replace,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function userResponse(verified: boolean) {
  return jsonResponse({
    id: "user-1",
    email: "ada@example.com",
    display_name: "Ada",
    is_verified: verified,
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
    requirements: [
      {
        id: "req-1",
        position: 0,
        identifier: "FR-001",
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
          start_offset: 7,
          end_offset: 36,
          line_start: 1,
          line_end: 1,
        },
        issues: [],
      },
    ],
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AnalyzerWorkspace", () => {
  it("runs input → preview → start-over with the draft preserved", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/me")) return userResponse(true);
        if (url.includes("/analysis")) return jsonResponse(analysisResult());
        throw new Error(`unexpected request: ${url}`);
      }),
    );
    render(
      <AuthProvider>
        <AnalyzerWorkspace />
      </AuthProvider>,
    );

    // Verified users get the workspace (title + explanation + editor).
    expect(await screen.findByRole("heading", { name: "Analyze requirements" })).toBeDefined();
    expect(
      screen.getByText(/Paste your SRS text below, or upload a PDF, DOCX, or TXT file/),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("SRS text"), {
      target: { value: "FR-001: The system shall allow login." },
    });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));

    // Result replaces the editor (score + the clean requirement).
    expect(await screen.findByText("Analysis complete · 1 requirement · 0 issues")).toBeDefined();
    expect(screen.getByText("The system shall allow login.")).toBeDefined();
    expect(screen.getByText("No issues — reads clearly.")).toBeDefined();
    expect(screen.queryByLabelText("SRS text")).toBeNull();

    // Starting over returns to the editor WITH the submission preserved.
    await user.click(screen.getByRole("button", { name: "Start over" }));
    expect(((await screen.findByLabelText("SRS text")) as HTMLTextAreaElement).value).toBe(
      "FR-001: The system shall allow login.",
    );
    expect(screen.queryByText("Analysis complete · 1 requirement · 0 issues")).toBeNull();
  });

  it("switches input methods via tabs (click + arrow keys)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => userResponse(true)),
    );
    render(
      <AuthProvider>
        <AnalyzerWorkspace />
      </AuthProvider>,
    );
    const pasteTab = await screen.findByRole("tab", { name: "Paste text" });
    const uploadTab = screen.getByRole("tab", { name: "Upload file" });
    expect(pasteTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByLabelText("SRS text")).toBeDefined();

    await user.click(uploadTab);
    expect(uploadTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByLabelText("SRS file")).toBeDefined();
    expect(screen.queryByLabelText("SRS text")).toBeNull();

    // Arrow keys move selection AND focus (automatic-activation tabs).
    uploadTab.focus();
    fireEvent.keyDown(uploadTab, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Paste text" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(document.activeElement?.textContent).toBe("Paste text");
    expect(await screen.findByLabelText("SRS text")).toBeDefined();
  });

  it("runs upload → result → start-over with the title preserved", async () => {
    const user = userEvent.setup();
    const uploadResult = {
      document: {
        id: "doc-1",
        filename: "srs.txt",
        file_type: "txt",
        mime_type: "text/plain",
        byte_size: 42,
        sha256: "abc123",
        extracted_chars: 42,
        extraction_status: "ok",
        created_at: "2026-09-24T00:00:00Z",
      },
      analysis: { ...analysisResult(), source_type: "document" },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/me")) return userResponse(true);
        if (url.includes("/documents/upload")) return jsonResponse(uploadResult, 201);
        throw new Error(`unexpected request: ${url}`);
      }),
    );
    render(
      <AuthProvider>
        <AnalyzerWorkspace />
      </AuthProvider>,
    );
    await user.click(await screen.findByRole("tab", { name: "Upload file" }));
    fireEvent.change(screen.getByLabelText("SRS file"), {
      target: { files: [new File(["FR-001: hi"], "srs.txt", { type: "text/plain" })] },
    });
    fireEvent.change(screen.getByLabelText("Title (optional)"), {
      target: { value: "Uploaded SRS" },
    });
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));

    expect(await screen.findByText("Analysis complete · 1 requirement · 0 issues")).toBeDefined();
    expect(screen.queryByLabelText("SRS file")).toBeNull();

    // Starting over returns to the UPLOAD tab with the title kept.
    await user.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.getByRole("tab", { name: "Upload file" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect((screen.getByLabelText("Title (optional)") as HTMLInputElement).value).toBe(
      "Uploaded SRS",
    );
  });

  it("allows any authenticated account to use the analyzer", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => userResponse(false)));
    render(<AuthProvider><AnalyzerWorkspace /></AuthProvider>);
    expect(await screen.findByRole("heading", { name: "Analyze requirements" })).toBeDefined();
    expect(screen.getByLabelText("SRS text")).toBeDefined();
  });

  it("links verified users to their analysis history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => userResponse(true)),
    );
    render(
      <AuthProvider>
        <AnalyzerWorkspace />
      </AuthProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Analyze requirements" })).toBeDefined();
    expect(screen.getByRole("link", { name: /View history/ })).toHaveProperty(
      "href",
      expect.stringContaining("/history"),
    );
  });

  it("redirects signed-out visitors to /login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { code: "unauthenticated", message: "no" } }, 401)),
    );
    render(
      <AuthProvider>
        <AnalyzerWorkspace />
      </AuthProvider>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByLabelText("SRS text")).toBeNull();
  });

  it("fresh-report AI retry re-reads into the ok state without leaving the result (Stage 17)", async () => {
    const user = userEvent.setup();
    const failed = { ...analysisResult(), ai_status: "failed", ai_error: "Provider timed out." };
    const recovered = {
      ...analysisResult(),
      ai_status: "ok",
      ai_overview: "Fresh overview.",
      ai_provider: "groq",
      ai_error: null,
    };
    let posts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.includes("/auth/me")) return userResponse(true);
        if (url.includes("/auth/refresh"))
          return jsonResponse({ error: { code: "unauthenticated", message: "no" } }, 401);
        if (url.includes("/retry-ai") && method === "POST") {
          posts += 1;
          return jsonResponse({
            ai_status: "ok",
            ai_overview: "Fresh overview.",
            ai_provider: "groq",
            ai_error: null,
          });
        }
        if (url.endsWith("/analysis") && method === "POST") return jsonResponse(failed);
        if (url.includes("/analysis/analysis-1") && method === "GET")
          return jsonResponse(recovered);
        throw new Error(`unexpected request: ${method} ${url}`);
      }),
    );
    render(
      <AuthProvider>
        <AnalyzerWorkspace />
      </AuthProvider>,
    );
    fireEvent.change(await screen.findByLabelText("SRS text"), {
      target: { value: "FR-001: The system shall allow login." },
    });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(await screen.findByRole("heading", { name: "AI enhancement failed" })).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "AI overview" })).toBeDefined();
    expect(screen.getByText("Fresh overview.")).toBeDefined();
    // Still the fresh result (not bounced to the editor, draft intact).
    expect(posts).toBe(1);
    expect(screen.getByRole("button", { name: "Start over" })).toBeDefined();
  });
});
