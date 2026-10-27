// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { DashboardTrendBucket } from "@/types/dashboard";

import { DashboardTrend } from "./DashboardTrend";

function buckets(): DashboardTrendBucket[] {
  return [
    { bucket: "2026-09-22", avg_score: null, analyses: 0, requirements: 0 },
    { bucket: "2026-09-23", avg_score: 76.5, analyses: 2, requirements: 5 },
    { bucket: "2026-09-24", avg_score: null, analyses: 1, requirements: 2 },
  ];
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DashboardTrend", () => {
  it("maps buckets into the chart summary, legend, and data table", async () => {
    const user = userEvent.setup();
    const onRange = vi.fn();
    render(
      <DashboardTrend
        range="30d"
        onRange={onRange}
        buckets={buckets()}
        improved={2}
        scored={5}
        stale={false}
      />,
    );
    expect(screen.getByRole("heading", { name: "Ambiguity score over time" })).toBeDefined();
    expect(screen.getByText("Average score (0–100)")).toBeDefined();
    expect(screen.getByText("Runs per bucket")).toBeDefined();
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(
      /3 runs in this window across 1 bucket with scored runs/,
    );

    const group = screen.getByRole("group", { name: "Trend range" });
    expect(
      within(group).getByRole("button", { name: "Last 30 days" }).getAttribute("aria-pressed"),
    ).toBe("true");
    await user.click(within(group).getByRole("button", { name: "Last 12 weeks" }));
    expect(onRange).toHaveBeenCalledWith("12w");

    await user.click(screen.getByText("View trend data as a table"));
    const table = screen.getByRole("table");
    expect(within(table).getByText("Sep 23")).toBeDefined();
    expect(within(table).getByText("76.5")).toBeDefined();
    expect(within(table).getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("2 of 5 scored runs scored above the previous run.")).toBeDefined();
  });

  it("labels weekly buckets as weeks and marks staleness as busy", () => {
    const { container } = render(
      <DashboardTrend
        range="12w"
        onRange={() => {}}
        buckets={[{ bucket: "2026-09-21", avg_score: 80, analyses: 1, requirements: 3 }]}
        improved={0}
        scored={1}
        stale={true}
      />,
    );
    expect(screen.getByText("Week of Sep 21")).toBeDefined();
    expect(container.querySelector('section[aria-busy="true"]')).not.toBeNull();
    expect(screen.getByText("0 of 1 scored run scored above the previous run.")).toBeDefined();
  });

  it("explains an empty window instead of charting zeros", () => {
    render(
      <DashboardTrend
        range="30d"
        onRange={() => {}}
        buckets={[
          { bucket: "2026-09-23", avg_score: null, analyses: 0, requirements: 0 },
          { bucket: "2026-09-24", avg_score: null, analyses: 0, requirements: 0 },
        ]}
        improved={0}
        scored={0}
        stale={false}
      />,
    );
    expect(screen.getByText(/None of your runs fall inside this window/)).toBeDefined();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("table")).toBeDefined();
    expect(screen.getByText(/No scored runs to compare yet/)).toBeDefined();
  });
});
