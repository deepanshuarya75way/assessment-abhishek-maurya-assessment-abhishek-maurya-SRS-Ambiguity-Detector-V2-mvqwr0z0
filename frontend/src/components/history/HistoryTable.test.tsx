// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisSummary } from "@/types/analysis";

import { HistoryTable } from "./HistoryTable";

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

const noop = () => {};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("HistoryTable", () => {
  it("renders one semantic row per analysis with persisted values verbatim", () => {
    const { container } = render(
      <HistoryTable
        items={[
          summary(),
          summary({
            id: "analysis-2",
            title: "Contract review",
            source_type: "document",
            document: { filename: "contract.pdf", file_type: "pdf" },
            score: 100,
            band: "low",
            requirements_count: 2,
            issues_count: 0,
          }),
        ]}
        stale={false}
        onDeleted={noop}
      />,
    );
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Analysis" })).toBeDefined();
    expect(within(table).getByRole("columnheader", { name: "Score" })).toBeDefined();
    expect(screen.getByText("Login SRS")).toBeDefined();
    expect(screen.getByText("78")).toBeDefined();
    expect(screen.getByText(/Moderate ambiguity/)).toBeDefined();
    expect(screen.getByText("Pasted SRS text")).toBeDefined();
    expect(screen.getByText("File contract.pdf (PDF)")).toBeDefined();
    expect(screen.getByText("100")).toBeDefined();
    expect(screen.getByText(/Low ambiguity/)).toBeDefined();
    expect(screen.getByText("3")).toBeDefined();
    expect(screen.getByText("5")).toBeDefined();
    expect(screen.getByText("2")).toBeDefined();
    expect(screen.getByText("0")).toBeDefined();
    expect(container.querySelector("caption")?.textContent).toMatch(/saved report/);
  });

  it("links titles and Open actions to the saved report, never exposes raw ids", () => {
    const { container } = render(
      <HistoryTable items={[summary({ id: "abc-123" })]} stale={false} onDeleted={noop} />,
    );
    const titleLink = screen.getByRole("link", { name: "Login SRS" });
    expect(titleLink.getAttribute("href")).toBe("/analysis/abc-123");
    const openLink = screen.getByRole("link", { name: "Open Login SRS" });
    expect(openLink.getAttribute("href")).toBe("/analysis/abc-123");
    expect(container.textContent).not.toContain("abc-123");
  });

  it("reads failed and unscored rows honestly instead of fabricating scores", () => {
    render(
      <HistoryTable
        items={[
          summary({ id: "f", title: "Broken run", status: "failed", score: null, band: null }),
          summary({ id: "s", title: "Old run", status: "segmented", score: null, band: null }),
        ]}
        stale={false}
        onDeleted={noop}
      />,
    );
    expect(screen.getByText("Failed")).toBeDefined();
    expect(screen.getByText("Not scored")).toBeDefined();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("marks stale pages busy and labels cells for the mobile card layout", () => {
    const { container } = render(
      <HistoryTable items={[summary()]} stale={true} onDeleted={noop} />,
    );
    const busy = screen.getByRole("table").closest("[aria-busy]");
    expect(busy?.getAttribute("aria-busy")).toBe("true");
    for (const label of ["Score", "Requirements", "Issues"]) {
      expect(container.querySelector(`td[data-label="${label}"]`)).not.toBeNull();
    }
  });

  it("deletes through the shared confirm dialog and notifies the parent", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const onDeleted = vi.fn();
    render(<HistoryTable items={[summary()]} stale={false} onDeleted={onDeleted} />);
    await user.click(screen.getByRole("button", { name: "Delete Login SRS" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(onDeleted).toHaveBeenCalledTimes(1);
  });
});
