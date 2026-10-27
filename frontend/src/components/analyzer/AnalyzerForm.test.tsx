// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisResult } from "@/types/analysis";

import { AnalyzerForm } from "./AnalyzerForm";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number, details: unknown = null): Response {
  return jsonResponse({ error: { code, message: `server ${code}`, details } }, status);
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

describe("AnalyzerForm", () => {
  it("renders the editor, counters, and actions", () => {
    render(<AnalyzerForm onResult={() => {}} />);
    expect(screen.getByLabelText("Title (optional)")).toBeDefined();
    expect(screen.getByLabelText("SRS text")).toBeDefined();
    expect(screen.getByText("0 / 200,000 characters · 0 words")).toBeDefined();
    expect(screen.getByRole("button", { name: "Analyze requirements" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Clear" })).toBeDefined();
  });

  it("updates character/word counts as text changes (counts, not segmentation)", async () => {
    const user = userEvent.setup();
    render(<AnalyzerForm onResult={() => {}} />);
    await user.type(screen.getByLabelText("SRS text"), "The system shall boot.");
    expect(screen.getByText("22 / 200,000 characters · 4 words")).toBeDefined();
  });

  it("blocks blank submit with an inline error and no request", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(analysisResult()));
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalyzerForm onResult={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(screen.getByText("Paste your SRS text to begin.")).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("blocks oversize input client-side with the submit disabled", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(analysisResult()));
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalyzerForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "x".repeat(200_001) } });
    expect(screen.getByText(/200,001 \/ 200,000 characters/)).toBeDefined();
    expect(screen.getByText("Keep your SRS under 200,000 characters.")).toBeDefined();
    const submit = screen.getByRole("button", { name: "Analyze requirements" });
    expect(submit.getAttribute("disabled")).not.toBeNull();
    fireEvent.click(submit);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("flags an over-long title live, with the submit disabled", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse(analysisResult()));
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalyzerForm onResult={() => {}} />);
    await user.type(screen.getByLabelText("Title (optional)"), "t".repeat(201));
    expect(screen.getByText("Keep the title under 200 characters.")).toBeDefined();
    const submit = screen.getByRole("button", { name: "Analyze requirements" });
    expect(submit.getAttribute("disabled")).not.toBeNull();
    fireEvent.click(submit);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits once, shows pending state, and reports the result + draft", async () => {
    const user = userEvent.setup();
    let release!: (value: Response) => void;
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }),
    );
    const onResult = vi.fn();
    render(<AnalyzerForm onResult={onResult} />);
    fireEvent.change(screen.getByLabelText("SRS text"), {
      target: { value: "FR-001: The system shall allow login." },
    });
    fireEvent.change(screen.getByLabelText("Title (optional)"), {
      target: { value: "Login SRS" },
    });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(
      screen.getByRole("button", { name: "Analyzing requirements…" }).getAttribute("disabled"),
    ).not.toBeNull();
    release(jsonResponse(analysisResult()));
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1));
    expect(onResult).toHaveBeenCalledWith(analysisResult(), {
      title: "Login SRS",
      text: "FR-001: The system shall allow login.",
    });
    expect(calls).toBe(1);
  });

  it("maps no_requirements_detected to guidance copy (never server strings)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("no_requirements_detected", 400)),
    );
    const onResult = vi.fn();
    render(<AnalyzerForm onResult={onResult} />);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "plain prose" } });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("couldn't find any requirements");
    expect(alert.textContent).not.toContain("server no_requirements_detected");
    expect(onResult).not.toHaveBeenCalled();
  });

  it("maps server text-length details onto the textarea", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        envelope("validation_error", 400, [{ loc: ["body", "text"], msg: "too long" }]),
      ),
    );
    render(<AnalyzerForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "FR-1: hi" } });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(await screen.findByText("Keep your SRS under 200,000 characters.")).toBeDefined();
  });

  it("reports an expired session when refresh fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/auth/refresh")
          ? envelope("invalid_token", 400)
          : envelope("unauthenticated", 401),
      ),
    );
    render(<AnalyzerForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "FR-1: hi" } });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(await screen.findByText("Your session has expired. Please log in again.")).toBeDefined();
  });

  it("reports network failures with the client's safe copy", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    render(<AnalyzerForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "FR-1: hi" } });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(await screen.findByText(/Could not reach the analysis service/)).toBeDefined();
  });

  it("clears fields and errors", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(analysisResult())),
    );
    render(<AnalyzerForm onResult={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(screen.getByText("Paste your SRS text to begin.")).toBeDefined();
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "FR-1: hi" } });
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect((screen.getByLabelText("SRS text") as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByText("Paste your SRS text to begin.")).toBeNull();
  });

  it("resumes with the provided draft", () => {
    render(
      <AnalyzerForm initial={{ title: "Draft", text: "FR-1: resumed" }} onResult={() => {}} />,
    );
    expect((screen.getByLabelText("Title (optional)") as HTMLInputElement).value).toBe("Draft");
    expect((screen.getByLabelText("SRS text") as HTMLTextAreaElement).value).toBe("FR-1: resumed");
  });

  it("sends ai_enhance false by default, true when the checkbox is checked", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        bodies.push(JSON.parse(String(init?.body)));
        return jsonResponse(analysisResult());
      }),
    );
    render(<AnalyzerForm onResult={() => {}} />);
    const checkbox = screen.getByRole("checkbox", { name: "Enhance with AI" });
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "FR-1: hi" } });
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ options: { ai_enhance: false } });
    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ options: { ai_enhance: true } });
  });

  it("links to Settings for provider management", () => {
    render(<AnalyzerForm onResult={() => {}} />);
    expect(
      screen.getByRole("link", { name: "Manage providers in Settings" }).getAttribute("href"),
    ).toBe("/settings");
  });

  it("names AI in the pending state when enhancement is checked", async () => {
    const user = userEvent.setup();
    let release!: (value: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Promise<Response>((resolve) => {
            release = resolve;
          }),
      ),
    );
    const onResult = vi.fn();
    render(<AnalyzerForm onResult={onResult} />);
    fireEvent.change(screen.getByLabelText("SRS text"), { target: { value: "FR-1: hi" } });
    await user.click(screen.getByRole("checkbox", { name: "Enhance with AI" }));
    await user.click(screen.getByRole("button", { name: "Analyze requirements" }));
    expect(screen.getByRole("button", { name: "Analyzing requirements with AI…" })).toBeDefined();
    release(jsonResponse(analysisResult()));
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1));
  });
});
