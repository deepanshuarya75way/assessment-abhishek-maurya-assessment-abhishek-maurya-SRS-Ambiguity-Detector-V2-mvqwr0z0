// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { CategoryBars } from "./CategoryBars";
import { HealthBars } from "./HealthBars";

afterEach(() => {
  cleanup();
});

describe("CategoryBars", () => {
  it("lists categories with counts, most-frequent first", () => {
    const { container } = render(
      <CategoryBars
        counts={[
          { category: "Subjective terms", count: 8 },
          { category: "Vague quantifiers", count: 3 },
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Issue categories" })).toBeDefined();
    const items = [...container.querySelectorAll("li")].map((li) => li.textContent);
    expect(items).toEqual(["Subjective terms8", "Vague quantifiers3"]);
    expect(screen.getByText(/this analysis only/)).toBeDefined();
  });

  it("renders nothing for clean analyses (no hollow chart)", () => {
    render(<CategoryBars counts={[]} />);
    expect(screen.queryByRole("heading", { name: "Issue categories" })).toBeNull();
  });

  it("accepts a dashboard caption and heading level", () => {
    render(
      <CategoryBars
        counts={[{ category: "Vague quantifiers", count: 4 }]}
        caption="Across all your analyses."
        headingLevel="h2"
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Issue categories" })).toBeDefined();
    expect(screen.getByText("Across all your analyses.")).toBeDefined();
    expect(screen.queryByText(/this analysis only/)).toBeNull();
  });
});

describe("HealthBars", () => {
  it("renders all four persisted dimensions as values, not decoration", () => {
    render(
      <HealthBars health={{ clarity: 70, specificity: 65, measurability: 58, completeness: 80 }} />,
    );
    expect(screen.getByRole("heading", { name: "Requirement health" })).toBeDefined();
    for (const [label, value] of [
      ["Clarity", "70"],
      ["Specificity", "65"],
      ["Measurability", "58"],
      ["Completeness", "80"],
    ]) {
      expect(screen.getByText(label as string)).toBeDefined();
      expect(screen.getByText(value as string)).toBeDefined();
    }
  });
});
