import { existsSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  DETECTED_AMBIGUITY_CATEGORIES,
  PUBLIC_CONTENT_ROUTES,
  RESOURCE_CARDS,
} from "./public-content";

function pageFileFor(path: string): string {
  const appRoot = join(process.cwd(), "src/app");
  if (path === "/") return join(appRoot, "page.tsx");
  return join(appRoot, path.slice(1), "page.tsx");
}

describe("public content routes", () => {
  it("points every public route at a real App Router page", () => {
    for (const route of PUBLIC_CONTENT_ROUTES) {
      expect(existsSync(pageFileFor(route.path)), `${route.path} page missing`).toBe(true);
      expect(route.description.length).toBeGreaterThan(30);
    }
  });

  it("keeps resource cards linked to public content routes", () => {
    const routes = new Set(PUBLIC_CONTENT_ROUTES.map((route) => route.path));
    for (const card of RESOURCE_CARDS) {
      expect(routes.has(card.href), `${card.href} is not in PUBLIC_CONTENT_ROUTES`).toBe(true);
      expect(card.title).toBeTruthy();
      expect(card.summary).not.toMatch(/#1|guaranteed|award|testimonial/i);
    }
  });
});

describe("documented ambiguity categories", () => {
  it("matches the deterministic detector registry names used publicly", () => {
    expect(DETECTED_AMBIGUITY_CATEGORIES.map((category) => category.detectorId)).toEqual([
      "vague-quantifier",
      "subjective-term",
      "missing-measurable-criteria",
      "ambiguous-operator",
      "undefined-terminology",
      "passive-actor",
      "pronoun-reference",
      "absolute-language",
      "optional-language",
      "missing-constraint",
      "incomplete-requirement",
    ]);
  });

  it("gives each category useful educational content without private data", () => {
    for (const category of DETECTED_AMBIGUITY_CATEGORIES) {
      expect(category.explanation.length).toBeGreaterThan(50);
      expect(category.example.length).toBeGreaterThan(12);
      expect(category.risk.length).toBeGreaterThan(40);
      expect(category.clarification.length).toBeGreaterThan(40);
      expect(JSON.stringify(category)).not.toMatch(
        /analysisId|documentName|sourceText|api_key|token/i,
      );
    }
  });
});
