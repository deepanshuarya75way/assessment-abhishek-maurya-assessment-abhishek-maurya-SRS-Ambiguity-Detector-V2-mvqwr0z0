// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { RequirementSeverity } from "@/types/analysis";

import { SeverityBadge } from "./SeverityBadge";

afterEach(() => {
  cleanup();
});

describe("SeverityBadge", () => {
  it.each([
    ["low", "Low"],
    ["medium", "Medium"],
    ["high", "High"],
    ["critical", "Critical"],
  ] as Array<[RequirementSeverity, string]>)(
    "renders the %s label as text (never color alone)",
    (severity, label) => {
      const { container } = render(<SeverityBadge severity={severity} />);
      // The label carries the meaning — screen readers + color-blind users
      // get the word, not just the dot.
      expect(screen.getByText(label)).toBeDefined();
      // The dot is decorative: hidden from assistive tech, inherits the color.
      const dot = container.querySelector('[aria-hidden="true"]');
      expect(dot?.className).toContain("bg-current");
    },
  );
});
