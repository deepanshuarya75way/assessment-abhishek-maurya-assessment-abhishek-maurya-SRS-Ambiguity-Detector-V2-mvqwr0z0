// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ScoreRing } from "./ScoreRing";

afterEach(() => {
  cleanup();
});

describe("ScoreRing", () => {
  it("renders the score, /100 scale, band label, and a text equivalent", () => {
    render(<ScoreRing score={70} band="high" />);
    expect(
      screen.getByRole("img", { name: "Ambiguity score 70 out of 100, high ambiguity" }),
    ).toBeDefined();
    expect(screen.getByText("High ambiguity")).toBeDefined();
    expect(screen.getByText("/100")).toBeDefined();
  });

  it("renders the honest unscored state instead of a zero ring", () => {
    render(<ScoreRing score={null} band={null} />);
    expect(screen.getByText("Not scored")).toBeDefined();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
