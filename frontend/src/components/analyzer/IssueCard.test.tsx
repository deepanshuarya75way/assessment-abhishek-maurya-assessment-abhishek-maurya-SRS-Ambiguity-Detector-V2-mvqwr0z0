// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisIssue } from "@/types/analysis";

import { IssueCard } from "./IssueCard";

function issue(): AnalysisIssue {
  return {
    id: "issue-1",
    detector_id: "vague-quantifier",
    category: "Vague quantifier",
    severity: "medium",
    phrase: "several",
    start_offset: 10,
    end_offset: 17,
    reason: "“several” has no agreed numeric meaning; reviewers will disagree on the count.",
    recommendation: "Replace “several” with the exact number or an explicit range.",
    ai_explanation: null,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("IssueCard", () => {
  it("shows category + severity + quoted phrase with the explanation collapsed", () => {
    render(<IssueCard issue={issue()} />);
    expect(screen.getByText("Vague quantifier")).toBeDefined();
    expect(screen.getByText("Medium")).toBeDefined();
    expect(screen.getByText("“several”")).toBeDefined();
    const toggle = screen.getByRole("button");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("expands to the why-flagged explanation with detector id and fix, then collapses", async () => {
    const user = userEvent.setup();
    render(<IssueCard issue={issue()} />);
    const toggle = screen.getByRole("button");

    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByRole("region", {
      name: "Why this was flagged: Vague quantifier",
    });
    expect(panel).toBeDefined();
    expect(screen.getByText("Why was this flagged?")).toBeDefined();
    expect(screen.getByText(/no agreed numeric meaning/)).toBeDefined();
    expect(screen.getByText("rule · vague-quantifier")).toBeDefined();
    expect(screen.getByText("Suggested fix")).toBeDefined();
    expect(screen.getByText(/exact number or an explicit range/)).toBeDefined();

    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("copies only the suggestion text (never detector internals)", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<IssueCard issue={issue()} />);
    await user.click(screen.getByRole("button", { name: /Vague quantifier/ }));
    await user.click(screen.getByRole("button", { name: "Copy suggestion" }));
    expect(writeText).toHaveBeenCalledWith(
      "Replace “several” with the exact number or an explicit range.",
    );
  });
});
