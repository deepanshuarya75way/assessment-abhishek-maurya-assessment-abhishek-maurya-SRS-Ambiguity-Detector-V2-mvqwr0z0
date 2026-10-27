import { describe, expect, it } from "vitest";

import { apiOrigin, buildReportOnlyCsp } from "./csp";

describe("apiOrigin", () => {
  it("extracts the origin from an API base URL", () => {
    expect(apiOrigin("https://api.example.com/v1")).toBe("https://api.example.com");
  });

  it("keeps explicit ports and drops trailing slashes", () => {
    expect(apiOrigin("http://localhost:8000/api/v1/")).toBe("http://localhost:8000");
  });

  it("falls back to the local API origin when unset", () => {
    expect(apiOrigin(undefined)).toBe("http://localhost:8000");
  });

  it("falls back to 'self' for unparseable input", () => {
    expect(apiOrigin("not a url")).toBe("'self'");
  });
});

describe("buildReportOnlyCsp", () => {
  it("allows only self plus the API origin for fetches", () => {
    const policy = buildReportOnlyCsp("https://api.example.com/v1");
    expect(policy).toContain("connect-src 'self' https://api.example.com");
    expect(policy).toContain("default-src 'self'");
  });

  it("hardens non-script directives", () => {
    const policy = buildReportOnlyCsp(undefined);
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'self'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("form-action 'self'");
    expect(policy).toContain("font-src 'self'");
  });

  it("permits Next inline runtime scripts (report-only observation)", () => {
    expect(buildReportOnlyCsp(undefined)).toContain("script-src 'self' 'unsafe-inline'");
  });
});
