import { describe, expect, it } from "vitest";

import { RESOURCE_CARDS } from "./public-content";
import {
  AUTH_ROUTES,
  PRIVATE_ROUTES,
  PUBLIC_ROUTES,
  absoluteUrl,
  articleStructuredData,
  breadcrumbStructuredData,
  homeStructuredData,
  normalizeSiteUrl,
  privatePageMetadata,
  publicPageMetadata,
  robotsPolicy,
  sitemapEntries,
} from "./seo";

const privateAndAuthRoutes = [...PRIVATE_ROUTES, ...AUTH_ROUTES];
const expectedPublicPaths = [
  "/",
  "/features",
  "/how-it-works",
  "/resources",
  "/resources/what-is-srs-ambiguity",
  "/resources/write-clearer-requirements",
];

describe("SEO site URL helpers", () => {
  it("normalizes canonical origins and strips paths/query strings", () => {
    expect(normalizeSiteUrl("https://example.com/app?utm=x")).toBe("https://example.com");
    expect(normalizeSiteUrl("https://example.com/")).toBe("https://example.com");
  });

  it("falls back to localhost for blank or invalid canonical input", () => {
    expect(normalizeSiteUrl("")).toBe("http://localhost:3000");
    expect(normalizeSiteUrl("not a url")).toBe("http://localhost:3000");
  });

  it("builds absolute URLs without preserving token query parameters", () => {
    expect(absoluteUrl("/reset-password")).toBe("http://localhost:3000/reset-password");
  });
});

describe("public metadata", () => {
  it("sets indexable metadata with canonical, Open Graph, and Twitter cards", () => {
    const metadata = publicPageMetadata({
      title: "SRS Ambiguity Detection Features",
      description: "Find ambiguous requirements.",
      path: "/features",
    });

    expect(metadata.robots).toEqual({ index: true, follow: true });
    expect(metadata.alternates?.canonical).toBe("http://localhost:3000/features");
    expect(metadata.openGraph).toMatchObject({
      type: "website",
      url: "http://localhost:3000/features",
      siteName: "SRS Ambiguity Detector",
    });
    expect(metadata.twitter).toMatchObject({ card: "summary_large_image" });
    expect(JSON.stringify(metadata)).toContain("/og/srs-ambiguity-detector.svg");
  });
});

describe("private metadata", () => {
  it("sets strict noindex/nofollow and omits canonical and social metadata", () => {
    const metadata = privatePageMetadata("Analysis result", "Private report");

    expect(metadata.robots).toMatchObject({
      index: false,
      follow: false,
      googleBot: { index: false, follow: false, noarchive: true, nosnippet: true },
    });
    expect(metadata.alternates).toBeUndefined();
    expect(metadata.openGraph).toBeUndefined();
    expect(metadata.twitter).toBeUndefined();
  });
});

describe("sitemap and robots policies", () => {
  it("includes the intended public content routes exactly once", () => {
    const sitemap = sitemapEntries();
    const urls = sitemap.map((entry) => entry.url);
    const paths = PUBLIC_ROUTES.map((route) => route.path);

    expect(paths).toEqual(expectedPublicPaths);
    expect(urls).toEqual(expectedPublicPaths.map((path) => absoluteUrl(path)));
    expect(new Set(urls).size).toBe(urls.length);
    for (const entry of sitemap) {
      expect(() => new URL(entry.url)).not.toThrow();
      expect(entry.lastModified).toBe("2026-09-24");
    }
  });

  it("excludes private, auth, token, API, and analysis detail URLs from the sitemap", () => {
    const serialized = JSON.stringify(sitemapEntries());
    for (const route of privateAndAuthRoutes) {
      expect(serialized).not.toContain(route);
    }
    expect(serialized).not.toContain("/api/");
    expect(serialized).not.toMatch(/token|analysis\/[^\"]+/i);
  });

  it("allows public routes but disallows API, private app, auth, and token-sensitive routes", () => {
    const robots = robotsPolicy();
    const rule = Array.isArray(robots.rules) ? robots.rules[0] : robots.rules;
    if (!rule) throw new Error("robots rule missing");

    expect(rule.allow).toEqual(expectedPublicPaths);
    expect(rule.disallow).toEqual(
      expect.arrayContaining(["/api/", ...privateAndAuthRoutes, "/*?token=", "/*&token="]),
    );
    expect(robots.sitemap).toBe("http://localhost:3000/sitemap.xml");
    expect(robots.host).toBe("http://localhost:3000");
  });
});

describe("structured data", () => {
  it("uses only real generic application data and avoids fake reviews or user content", () => {
    const data = homeStructuredData();
    const serialized = JSON.stringify(data);

    expect(data.map((entry) => entry["@type"])).toEqual(["WebSite", "SoftwareApplication"]);
    expect(serialized).toContain("SRS Ambiguity Detector");
    expect(serialized).not.toMatch(/aggregateRating|review|award|testimonial|price|Offer/i);
    expect(serialized).not.toMatch(/token|session|email|analysisId|documentName|sourceText/i);
  });

  it("builds breadcrumb and article JSON-LD without fabricated fields", () => {
    const breadcrumb = breadcrumbStructuredData([
      { name: "Home", path: "/" },
      { name: "Resources", path: "/resources" },
    ]);
    const article = articleStructuredData({
      title: "What Is SRS Ambiguity?",
      description: "Understand ambiguity in requirements.",
      path: "/resources/what-is-srs-ambiguity",
    });
    const serialized = JSON.stringify([breadcrumb, article]);

    expect(breadcrumb["@type"]).toBe("BreadcrumbList");
    expect(article["@type"]).toBe("Article");
    expect(serialized).toContain("http://localhost:3000/resources/what-is-srs-ambiguity");
    expect(serialized).not.toMatch(/aggregateRating|review|award|testimonial/i);
  });
});

describe("public content registry", () => {
  it("keeps resource cards pointing at public indexed routes", () => {
    const publicPaths = new Set(PUBLIC_ROUTES.map((route) => route.path));
    for (const card of RESOURCE_CARDS) {
      expect(publicPaths.has(card.href)).toBe(true);
      expect(card.summary.length).toBeGreaterThan(40);
    }
  });
});
