// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { SeverityMix } from "./SeverityMix";

afterEach(() => {
  cleanup();
});

describe("SeverityMix", () => {
  it("renders the complete vocabulary as real text plus a labeled bar", () => {
    render(
      <SeverityMix
        total={8}
        counts={[
          { severity: "low", count: 1 },
          { severity: "medium", count: 2 },
          { severity: "high", count: 5 },
          { severity: "critical", count: 0 },
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Issue severity" })).toBeDefined();
    expect(screen.getByText("Low")).toBeDefined();
    expect(screen.getByText("Critical")).toBeDefined();
    expect(screen.getByText("5")).toBeDefined();
    expect(screen.getByText("0")).toBeDefined();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "Severity mix: 1 low, 2 medium, 5 high",
    );
  });

  it("explains zero issues instead of a hollow bar", () => {
    render(
      <SeverityMix
        total={0}
        counts={[
          { severity: "low", count: 0 },
          { severity: "medium", count: 0 },
          { severity: "high", count: 0 },
          { severity: "critical", count: 0 },
        ]}
      />,
    );
    expect(screen.getByText(/No issues found across your analyses yet/)).toBeDefined();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getAllByText("0")).toHaveLength(4);
  });
});
