// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisResult, ScoreBreakdown, SegmentedRequirement } from "@/types/analysis";

import { AnalysisResultView } from "./AnalysisResultView";

function requirement(overrides: Partial<SegmentedRequirement> = {}): SegmentedRequirement {
  return {
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
    ...overrides,
  };
}

function cleanRequirement(): SegmentedRequirement {
  return requirement({
    id: "req-2",
    position: 1,
    identifier: "FR-002",
    text: "The system shall allow login.",
    score: 100,
    severity: null,
    issues_count: 0,
    segmentation: {
      strategy: "requirement_id",
      confidence: 0.95,
      start_offset: 28,
      end_offset: 57,
      line_start: 2,
      line_end: 2,
    },
    issues: [],
  });
}

function result(): AnalysisResult {
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
    requirements: [requirement(), cleanRequirement()],
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
  };
}

/** No deductions exist for failed/segmented rows (wire sends `{}`; same zeros). */
const EMPTY_BREAKDOWN: ScoreBreakdown = {
  base: 100,
  deductions: [],
  counts: { low: 0, medium: 0, high: 0, critical: 0 },
};

function failedResult(): AnalysisResult {
  return {
    ...result(),
    status: "failed",
    score: null,
    band: null,
    score_breakdown: EMPTY_BREAKDOWN,
    requirements_count: 0,
    issues_count: 0,
    health: null,
    requirements: [],
  };
}

afterEach(() => {
  cleanup();
});

describe("AnalysisResultView", () => {
  it("renders counts, score, severity grid, honesty footnote, and both cards", () => {
    const { container } = render(
      <AnalysisResultView result={result()} actions={<button type="button">Stub action</button>} />,
    );

    expect(screen.getByText("Analysis complete · 2 requirements · 1 issue")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Login SRS" })).toBeDefined();
    expect(
      screen.getByRole("img", { name: "Ambiguity score 85 out of 100, low ambiguity" }),
    ).toBeDefined();

    // Requirements, issues, then low/medium/high/critical counts in order.
    const values = [...container.querySelectorAll("dd")].map((dd) => dd.textContent);
    expect(values).toEqual(["2", "1", "0", "0", "1", "0"]);

    expect(screen.getByText(/transparent heuristic indicator/)).toBeDefined();
    // The first requirement's text is split by a <mark> — assert on full content.
    expect(container.querySelector("ol")?.textContent).toContain("The service should be fast.");
    expect(screen.getByText("The system shall allow login.")).toBeDefined();
    expect(screen.getByText("No issues — reads clearly.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Stub action" })).toBeDefined();
  });

  it("shows date + pasted-text source in the meta line, with severity-mix summary", () => {
    render(<AnalysisResultView result={result()} />);
    expect(screen.getByText(/Analyzed .* · Pasted SRS text/)).toBeDefined();
    expect(screen.getByRole("img", { name: "Severity mix: 1 high" })).toBeDefined();
  });

  it("shows category + health overviews for analyzed results with issues", () => {
    render(<AnalysisResultView result={result()} />);
    expect(screen.getByRole("heading", { name: "Issue categories" })).toBeDefined();
    expect(screen.getByText("Subjective term")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Requirement health" })).toBeDefined();
    expect(screen.getByText("Measurability")).toBeDefined();
  });

  it("saved context reads as a saved report with the same numbers", () => {
    const { container } = render(<AnalysisResultView result={result()} context="saved" />);
    expect(screen.getByText("Saved analysis · 2 requirements · 1 issue")).toBeDefined();
    expect(screen.getByText(/Saved .* · Pasted SRS text/)).toBeDefined();
    const values = [...container.querySelectorAll("dd")].map((dd) => dd.textContent);
    expect(values).toEqual(["2", "1", "0", "0", "1", "0"]);
  });

  it("names the source file for document analyses", () => {
    render(
      <AnalysisResultView
        result={{
          ...result(),
          source_type: "document",
          document: { filename: "contract.pdf", file_type: "pdf" },
        }}
        context="saved"
      />,
    );
    expect(screen.getByText(/File contract\.pdf \(PDF\)/)).toBeDefined();
  });

  it("failed analyses show the failure panel with no scores, plus footer actions", () => {
    render(
      <AnalysisResultView
        result={failedResult()}
        context="saved"
        actions={<button type="button">Back to Analyzer</button>}
      />,
    );
    expect(screen.getByText("Saved analysis · failed")).toBeDefined();
    expect(screen.getByRole("heading", { name: "This analysis did not complete" })).toBeDefined();
    expect(screen.getByText(/none were produced/)).toBeDefined();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText("Showing all 0 requirements")).toBeNull();
    expect(screen.getByRole("button", { name: "Back to Analyzer" })).toBeDefined();
  });

  it("segmented analyses list requirements unscored with an honest notice", () => {
    const unscored = (id: string, position: number, text: string) =>
      requirement({
        id,
        position,
        identifier: null,
        text,
        score: null,
        severity: null,
        issues_count: 0,
        issues: [],
      });
    render(
      <AnalysisResultView
        result={{
          ...result(),
          status: "segmented",
          score: null,
          band: null,
          score_breakdown: EMPTY_BREAKDOWN,
          health: null,
          requirements: [
            unscored("req-1", 0, "The service should be fast."),
            unscored("req-2", 1, "The system shall allow login."),
          ],
        }}
      />,
    );
    expect(screen.getByText(/Scored with an older version/)).toBeDefined();
    expect(screen.getByText("Not scored")).toBeDefined();
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.queryByRole("heading", { name: "Issue categories" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Requirement health" })).toBeNull();
  });

  it("clean analyses celebrate honestly without hollow charts", () => {
    render(
      <AnalysisResultView
        result={{
          ...result(),
          score: 100,
          issues_count: 0,
          score_breakdown: {
            base: 100,
            deductions: [],
            counts: { low: 0, medium: 0, high: 0, critical: 0 },
          },
          requirements: [
            cleanRequirement(),
            { ...cleanRequirement(), id: "req-3", position: 2, identifier: "FR-003" },
          ],
          requirements_count: 2,
        }}
      />,
    );
    expect(screen.getByText("No ambiguity issues detected")).toBeDefined();
    expect(screen.getByText(/did not identify any supported ambiguity patterns/)).toBeDefined();
    expect(screen.queryByRole("img", { name: /Severity mix/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Issue categories" })).toBeNull();
  });

  it("search narrows the list by text or identifier and announces the count", async () => {
    const user = userEvent.setup();
    render(<AnalysisResultView result={result()} />);
    expect(screen.getByText("Showing all 2 requirements")).toBeDefined();

    await user.type(screen.getByLabelText("Search"), "login");
    expect(screen.getByText("Showing 1 of 2 requirements")).toBeDefined();
    expect(screen.getByText("The system shall allow login.")).toBeDefined();
    expect(screen.queryByText("FR-001")).toBeNull();

    await user.clear(screen.getByLabelText("Search"));
    await user.type(screen.getByLabelText("Search"), "FR-001");
    expect(screen.getByText("Showing 1 of 2 requirements")).toBeDefined();
    expect(screen.getByText("FR-001")).toBeDefined();
    expect(screen.queryByText("FR-002")).toBeNull();
  });

  it("status and severity filters combine, with an honest empty state + reset", async () => {
    const user = userEvent.setup();
    render(<AnalysisResultView result={result()} />);

    await user.selectOptions(screen.getByLabelText("Status"), "clean");
    expect(screen.getByText("Showing 1 of 2 requirements")).toBeDefined();
    expect(screen.getByText("The system shall allow login.")).toBeDefined();

    await user.selectOptions(screen.getByLabelText("Severity"), "high");
    expect(screen.getByText("No requirements match")).toBeDefined();
    expect(screen.queryByText("FR-001")).toBeNull();
    expect(screen.queryByText("FR-002")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByText("Showing all 2 requirements")).toBeDefined();
    expect((screen.getByLabelText("Status") as HTMLSelectElement).value).toBe("all");
  });

  it("sorts lowest-score-first while defaulting to original order", async () => {
    const user = userEvent.setup();
    const cleanFirst: AnalysisResult = {
      ...result(),
      requirements: [
        { ...cleanRequirement(), id: "req-a", position: 0 },
        { ...requirement(), id: "req-b", position: 1 },
      ],
    };
    const { container } = render(<AnalysisResultView result={cleanFirst} />);
    const chips = () =>
      [...container.querySelectorAll("ol > li")].map(
        (item) => item.querySelector("div > span")?.textContent,
      );
    expect(chips()).toEqual(["R-1", "R-2"]);

    await user.selectOptions(screen.getByLabelText("Sort"), "lowest-score");
    expect(chips()).toEqual(["R-2", "R-1"]);

    await user.selectOptions(screen.getByLabelText("Sort"), "original");
    expect(chips()).toEqual(["R-1", "R-2"]);
  });

  it("expand-all opens every visible requirement, collapse-all closes them", async () => {
    const user = userEvent.setup();
    render(<AnalysisResultView result={result()} />);
    expect(screen.queryByRole("region", { name: /Detected issues/ })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Expand all" }));
    expect(screen.getByRole("region", { name: "Detected issues for requirement 1" })).toBeDefined();

    await user.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByRole("region", { name: /Detected issues/ })).toBeNull();
  });

  it("hides the toolbar for single-requirement reports", () => {
    render(
      <AnalysisResultView
        result={{ ...result(), requirements: [requirement()], requirements_count: 1 }}
      />,
    );
    expect(screen.queryByLabelText("Search")).toBeNull();
    expect(screen.queryByRole("button", { name: "Expand all" })).toBeNull();
    expect(screen.getByText("FR-001")).toBeDefined();
  });

  it("renders the AI outcome block (overview + attribution + rewrite) on an enhanced run", () => {
    render(
      <AnalysisResultView
        result={{
          ...result(),
          ai_status: "ok",
          ai_provider: "groq",
          ai_overview: "Tighten the vague bounds.",
          requirements: [
            requirement({
              suggested_rewrite: "The service shall respond fast.",
              suggestion_source: "ai",
            }),
          ],
          requirements_count: 1,
        }}
      />,
    );
    expect(screen.getByRole("heading", { name: "AI overview" })).toBeDefined();
    expect(screen.getByText("Generated by Groq")).toBeDefined();
    expect(screen.getByText("Tighten the vague bounds.")).toBeDefined();
    expect(screen.getByText("AI-suggested rewrite")).toBeDefined();
  });

  it("renders the unconfigured empty state with a Settings CTA", () => {
    render(<AnalysisResultView result={{ ...result(), ai_status: "unconfigured" }} />);
    expect(
      screen.getByRole("heading", { name: "AI enhancement isn't configured yet" }),
    ).toBeDefined();
    expect(screen.getByRole("link", { name: "Open Settings" }).getAttribute("href")).toBe(
      "/settings",
    );
  });

  it("orders deterministic overviews before the AI block before requirements", () => {
    render(
      <AnalysisResultView
        result={{
          ...result(),
          ai_status: "ok",
          ai_provider: "groq",
          ai_overview: "Tighten the vague bounds.",
        }}
      />,
    );
    const categories = screen.getByRole("heading", { name: "Issue categories" });
    const health = screen.getByRole("heading", { name: "Requirement health" });
    const ai = screen.getByRole("heading", { name: "AI overview" });
    const following = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(categories.compareDocumentPosition(ai) & following).toBeTruthy();
    expect(health.compareDocumentPosition(ai) & following).toBeTruthy();
    expect(ai.compareDocumentPosition(screen.getByText("FR-001")) & following).toBeTruthy();
  });

  it("derives the partial-rewrite note from the persisted record", () => {
    render(
      <AnalysisResultView
        result={{
          ...result(),
          ai_status: "ok",
          ai_provider: "groq",
          ai_overview: "Overview.",
          requirements: [
            requirement({
              suggested_rewrite: "Rewritten.",
              suggestion_source: "ai",
            }),
            requirement({ id: "req-2", position: 1, identifier: "FR-002" }),
          ],
          requirements_count: 2,
        }}
      />,
    );
    expect(screen.getByText("AI rewrites cover 1 of 2 flagged requirements.")).toBeDefined();
  });

  it("renders the identical AI block on the saved report (no regeneration)", () => {
    render(
      <AnalysisResultView
        context="saved"
        result={{
          ...result(),
          ai_status: "ok",
          ai_provider: "openai",
          ai_overview: "Persisted overview.",
        }}
      />,
    );
    expect(screen.getByRole("heading", { name: "AI overview" })).toBeDefined();
    expect(screen.getByText("Generated by OpenAI")).toBeDefined();
    expect(screen.getByText("Persisted overview.")).toBeDefined();
  });

  it("failed AI renders Try again only when the parent passes onAiRetried", () => {
    const failed = { ...result(), ai_status: "failed" as const, ai_error: "Provider timed out." };
    const { rerender } = render(<AnalysisResultView result={failed} />);
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    rerender(<AnalysisResultView result={failed} onAiRetried={async () => undefined} />);
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
  });
});
