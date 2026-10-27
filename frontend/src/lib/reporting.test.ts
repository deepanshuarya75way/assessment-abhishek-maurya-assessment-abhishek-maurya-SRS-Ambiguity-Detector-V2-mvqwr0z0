import { describe, expect, it } from "vitest";

import type { AnalysisIssue, SegmentedRequirement } from "../types/analysis";

import {
  countByCategory,
  countBySeverity,
  filterRequirements,
  requirementHealth,
  sortRequirements,
} from "./reporting";

function issue(overrides: Partial<AnalysisIssue> = {}): AnalysisIssue {
  return {
    id: "issue-1",
    detector_id: "subjective-term",
    category: "Subjective terms",
    severity: "medium",
    phrase: "fast",
    start_offset: 0,
    end_offset: 4,
    reason: "reason",
    recommendation: "fix",
    ai_explanation: null,
    ...overrides,
  };
}

function requirement(overrides: Partial<SegmentedRequirement> = {}): SegmentedRequirement {
  return {
    id: "req-1",
    position: 0,
    identifier: null,
    section: null,
    text: "The system shall allow login.",
    score: 100,
    severity: null,
    issues_count: 0,
    suggested_rewrite: null,
    suggestion_source: null,
    segmentation: {
      strategy: "paragraph",
      confidence: 0.5,
      start_offset: 0,
      end_offset: 28,
      line_start: 1,
      line_end: 1,
    },
    issues: [],
    ...overrides,
  };
}

describe("requirementHealth", () => {
  it("labels unscored, clean, and per-severity states", () => {
    expect(requirementHealth(requirement({ score: null }))).toEqual({
      state: "not-scored",
      label: "Not scored",
    });
    expect(requirementHealth(requirement())).toEqual({ state: "healthy", label: "Healthy" });
    expect(
      requirementHealth(
        requirement({ score: 90, severity: "low", issues: [issue({ severity: "low" })] }),
      ).label,
    ).toBe("Needs attention");
    expect(
      requirementHealth(
        requirement({ score: 80, severity: "medium", issues: [issue({ severity: "medium" })] }),
      ).label,
    ).toBe("Needs attention");
    expect(
      requirementHealth(
        requirement({ score: 70, severity: "high", issues: [issue({ severity: "high" })] }),
      ),
    ).toEqual({ state: "high-ambiguity", label: "High ambiguity" });
    expect(
      requirementHealth(
        requirement({
          score: 60,
          severity: "critical",
          issues: [issue({ severity: "critical" })],
        }),
      ),
    ).toEqual({ state: "critical", label: "Critical" });
  });
});

describe("countByCategory", () => {
  it("counts most-frequent-first with stable ties", () => {
    const rows = [
      requirement({
        issues: [issue({ category: "B" }), issue({ category: "A" }), issue({ category: "B" })],
      }),
      requirement({ position: 1, issues: [issue({ category: "A" })] }),
    ];
    expect(countByCategory(rows)).toEqual([
      { category: "B", count: 2 },
      { category: "A", count: 2 },
    ]);
  });

  it("returns [] for clean analyses (no phantom categories)", () => {
    expect(countByCategory([requirement()])).toEqual([]);
  });
});

describe("countBySeverity", () => {
  it("keeps all four keys with honest zeros", () => {
    const rows = [requirement({ issues: [issue({ severity: "high" })] })];
    expect(countBySeverity(rows)).toEqual({ low: 0, medium: 0, high: 1, critical: 0 });
  });
});

describe("filterRequirements", () => {
  const rows = [
    requirement({ id: "r1", position: 0, text: "The service should be fast." }),
    requirement({
      id: "r2",
      position: 1,
      identifier: "FR-002",
      text: "The system shall allow login.",
      score: 70,
      severity: "high",
      issues: [issue({ severity: "high" })],
    }),
  ];

  it("filters by status", () => {
    expect(
      filterRequirements(rows, { query: "", status: "with-issues", severity: "all" }).map(
        (r) => r.id,
      ),
    ).toEqual(["r2"]);
    expect(
      filterRequirements(rows, { query: "", status: "clean", severity: "all" }).map((r) => r.id),
    ).toEqual(["r1"]);
  });

  it("filters by requirement severity", () => {
    expect(
      filterRequirements(rows, { query: "", status: "all", severity: "high" }).map((r) => r.id),
    ).toEqual(["r2"]);
    expect(filterRequirements(rows, { query: "", status: "all", severity: "low" })).toEqual([]);
  });

  it("searches text and identifier case-insensitively", () => {
    expect(
      filterRequirements(rows, { query: "LOGIN", status: "all", severity: "all" }).map((r) => r.id),
    ).toEqual(["r2"]);
    expect(
      filterRequirements(rows, { query: "fr-002", status: "all", severity: "all" }).map(
        (r) => r.id,
      ),
    ).toEqual(["r2"]);
    expect(filterRequirements(rows, { query: "absent", status: "all", severity: "all" })).toEqual(
      [],
    );
  });
});

describe("sortRequirements", () => {
  const rows = [
    requirement({ id: "r1", position: 2, score: 100 }),
    requirement({
      id: "r2",
      position: 0,
      score: 70,
      severity: "high",
      issues: [issue({ severity: "high" }), issue({ id: "i2", severity: "low" })],
    }),
    requirement({ id: "r3", position: 1, score: null }),
  ];

  it("defaults to explicit SRS position order", () => {
    expect(sortRequirements(rows, "original").map((r) => r.id)).toEqual(["r2", "r3", "r1"]);
  });

  it("sorts lowest-score-first with unscored last, ties by position", () => {
    expect(sortRequirements(rows, "lowest-score").map((r) => r.id)).toEqual(["r2", "r1", "r3"]);
  });

  it("sorts most-issues-first with ties by position", () => {
    expect(sortRequirements(rows, "most-issues").map((r) => r.id)).toEqual(["r2", "r3", "r1"]);
  });
});
