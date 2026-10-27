// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { AnalysisSummary } from "@/types/analysis";

import { RecentAnalyses } from "./RecentAnalyses";

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

afterEach(() => {
  cleanup();
});

describe("RecentAnalyses", () => {
  it("links each run to its saved report with persisted score vocabulary", () => {
    render(
      <RecentAnalyses
        items={[
          summary(),
          summary({
            id: "analysis-2",
            title: "Contract review",
            source_type: "document",
            document: { filename: "contract.pdf", file_type: "pdf" },
            score: 100,
            band: "low",
          }),
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Recent analyses" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Login SRS" })).toHaveProperty(
      "href",
      expect.stringContaining("/analysis/analysis-1"),
    );
    expect(screen.getByText("78 · Moderate ambiguity")).toBeDefined();
    expect(screen.getByText(/File contract\.pdf/)).toBeDefined();
    expect(screen.getByRole("link", { name: /View full history/ })).toHaveProperty(
      "href",
      expect.stringContaining("/history"),
    );
  });

  it("reads failed and unscored runs honestly", () => {
    render(
      <RecentAnalyses
        items={[
          summary({ id: "f", title: "Broken", status: "failed", score: null, band: null }),
          summary({ id: "s", title: "Old", status: "segmented", score: null, band: null }),
        ]}
      />,
    );
    expect(screen.getByText("Failed")).toBeDefined();
    expect(screen.getByText("Not scored")).toBeDefined();
  });

  it("renders nothing without items", () => {
    const { container } = render(<RecentAnalyses items={[]} />);
    expect(container.textContent).toBe("");
  });
});
