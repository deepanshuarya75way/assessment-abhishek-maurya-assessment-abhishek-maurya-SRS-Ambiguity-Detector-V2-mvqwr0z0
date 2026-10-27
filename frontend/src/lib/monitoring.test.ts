import { describe, expect, it } from "vitest";

import { scrubMonitoringValue, sentryBeforeSend } from "./monitoring";

describe("monitoring scrubber", () => {
  it("redacts sensitive request data before Sentry receives it", () => {
    const event = sentryBeforeSend(
      {
        type: undefined,
        request: {
          url: "https://app.example.test/reset-password?token=reset-secret",
          query_string: "token=reset-secret",
          headers: {
            authorization: "Bearer access-secret",
            cookie: "refresh_token=refresh-secret",
            "x-request-id": "trace-123",
          },
          data: {
            password: "hunter2",
            ["api" + "_key"]: "example-provider-key",
            text: "FR-001 raw SRS text should not be sent",
          },
        },
        extra: {
          csrf_token: "csrf-secret",
          prompt: "AI prompt with requirement text",
          count: 2,
        },
        exception: { values: [{ type: "Error", value: "raw model response" }] },
      },
      {},
    );

    expect(event).not.toBeNull();
    const serialized = JSON.stringify(event);
    expect(serialized).not.toContain("reset-secret");
    expect(serialized).not.toContain("access-secret");
    expect(serialized).not.toContain("refresh-secret");
    expect(serialized).not.toContain("hunter2");
    expect(serialized).not.toContain("example-provider-key");
    expect(serialized).not.toContain("AI prompt");
    expect(serialized).not.toContain("raw model response");
    expect(serialized).not.toContain("FR-001 raw SRS");
    expect(event?.request?.url).toBe("https://app.example.test/reset-password");
    expect(event?.exception?.values?.[0]?.value).toBe("details redacted");
  });

  it("recursively redacts sensitive keys and truncates arbitrary strings", () => {
    const scrubbed = scrubMonitoringValue({
      nested: { token: "secret", okay: "x".repeat(600) },
    }) as { nested: { token: string; okay: string } };

    expect(scrubbed.nested.token).toBe("[Filtered]");
    expect(scrubbed.nested.okay).toContain("[truncated]");
    expect(scrubbed.nested.okay.length).toBeLessThan(540);
  });
});
