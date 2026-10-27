import { describe, expect, it } from "vitest";

import { metadata as resetPasswordMetadata } from "./(auth)/reset-password/page";
import { metadata as loginMetadata } from "./(auth)/login/page";
import { metadata as signupMetadata } from "./(auth)/signup/page";
import { metadata as forgotPasswordMetadata } from "./(auth)/forgot-password/page";
import { metadata as analysisMetadata } from "./analysis/[id]/page";
import { metadata as analyzerMetadata } from "./analyzer/page";
import { metadata as dashboardMetadata } from "./dashboard/page";
import { metadata as featuresMetadata } from "./features/page";
import { metadata as historyMetadata } from "./history/page";
import { metadata as howItWorksMetadata } from "./how-it-works/page";
import { metadata as notFoundMetadata } from "./not-found";
import { metadata as homeMetadata } from "./page";
import { metadata as resourcesMetadata } from "./resources/page";
import { metadata as ambiguityResourceMetadata } from "./resources/what-is-srs-ambiguity/page";
import { metadata as clearerRequirementsMetadata } from "./resources/write-clearer-requirements/page";
import robots from "./robots";
import { metadata as settingsMetadata } from "./settings/page";
import sitemap from "./sitemap";

const privateRouteMetadata = [
  analysisMetadata,
  analyzerMetadata,
  dashboardMetadata,
  historyMetadata,
  settingsMetadata,
  notFoundMetadata,
];

const authRouteMetadata = [
  loginMetadata,
  signupMetadata,
  forgotPasswordMetadata,
  resetPasswordMetadata,
];

const publicMetadata = [
  { path: "/", metadata: homeMetadata, title: "Requirements ambiguity analysis" },
  { path: "/features", metadata: featuresMetadata, title: "Features" },
  { path: "/how-it-works", metadata: howItWorksMetadata, title: "How" },
  { path: "/resources", metadata: resourcesMetadata, title: "Resources" },
  {
    path: "/resources/what-is-srs-ambiguity",
    metadata: ambiguityResourceMetadata,
    title: "SRS Ambiguity",
  },
  {
    path: "/resources/write-clearer-requirements",
    metadata: clearerRequirementsMetadata,
    title: "Clearer",
  },
];

function expectNoindex(metadata: typeof analysisMetadata) {
  expect(metadata.robots).toMatchObject({
    index: false,
    follow: false,
    googleBot: { index: false, follow: false },
  });
  expect(metadata.alternates).toBeUndefined();
  expect(metadata.openGraph).toBeUndefined();
  expect(metadata.twitter).toBeUndefined();
}

describe("route SEO contracts", () => {
  it("publishes indexable metadata for every public content page", () => {
    for (const route of publicMetadata) {
      expect(String(route.metadata.title)).toContain(route.title);
      expect(route.metadata.description).toBeTruthy();
      expect(route.metadata.robots).toEqual({ index: true, follow: true });
      expect(route.metadata.alternates?.canonical).toBe(`http://localhost:3000${route.path}`);
      expect(route.metadata.openGraph).toMatchObject({
        type: "website",
        url: `http://localhost:3000${route.path}`,
        siteName: "SRS Ambiguity Detector",
      });
      expect(route.metadata.twitter).toMatchObject({ card: "summary_large_image" });
    }
  });

  it("keeps app, report, and 404 routes non-indexable with no public social metadata", () => {
    for (const metadata of privateRouteMetadata) {
      expectNoindex(metadata);
    }
  });

  it("keeps auth and token-capable routes non-indexable and free of canonical query leakage", () => {
    for (const metadata of authRouteMetadata) {
      expectNoindex(metadata);
      expect(JSON.stringify(metadata)).not.toMatch(/token|session|email=/i);
    }
  });

  it("generates a public-only sitemap", () => {
    const urls = sitemap().map((entry) => entry.url);
    expect(urls).toEqual(publicMetadata.map((route) => `http://localhost:3000${route.path}`));
    expect(JSON.stringify(urls)).not.toMatch(
      /\/analysis\/|\/analyzer|\/dashboard|\/history|\/settings|\/login|\/signup|reset-password|token|\/api\//i,
    );
  });

  it("disallows private, auth, API, and token-sensitive paths in robots.txt", () => {
    const policy = robots();
    const rule = Array.isArray(policy.rules) ? policy.rules[0] : policy.rules;
    if (!rule) throw new Error("robots rule missing");

    expect(rule.allow).toEqual(publicMetadata.map((route) => route.path));
    expect(rule.disallow).toEqual(
      expect.arrayContaining([
        "/api/",
        "/analysis/",
        "/analyzer",
        "/dashboard",
        "/history",
        "/settings",
        "/login",
        "/signup",
        "/forgot-password",
        "/reset-password",
        "/*?token=",
        "/*&token=",
      ]),
    );
  });
});
