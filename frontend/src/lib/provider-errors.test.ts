import { describe, expect, it } from "vitest";

import { ApiRequestError } from "./api";
import { providerErrorMessage, providerFieldErrors } from "./provider-errors";

function coded(code: string, details: unknown = null): ApiRequestError {
  return new ApiRequestError(400, {
    code,
    message: "Server copy (never displayed).",
    details,
  });
}

describe("provider error copy", () => {
  it("falls back safely for unknown shapes", () => {
    expect(providerErrorMessage(new Error("boom"), "load")).toBe(
      "Something went wrong. Please try again.",
    );
    expect(providerErrorMessage(coded("some_future_code"), "create")).toBe(
      "Something went wrong. Please try again.",
    );
  });

  it("maps the not-found code without an oracle", () => {
    expect(providerErrorMessage(coded("ai_provider_not_found"), "delete")).toBe(
      "That credential doesn't exist or belongs to a different account.",
    );
  });

  it("tailors conflict copy to the action", () => {
    expect(providerErrorMessage(coded("conflict"), "create")).toContain("Replace the existing");
    expect(providerErrorMessage(coded("conflict"), "rotate")).toContain("already stored");
    expect(providerErrorMessage(coded("conflict"), "update")).toContain("refresh the list");
    expect(providerErrorMessage(coded("conflict"), "delete")).toContain("Refresh the list");
  });

  it("maps validation, session, verification, and permission codes", () => {
    expect(providerErrorMessage(coded("validation_error"), "create")).toContain(
      "highlighted fields",
    );
    expect(providerErrorMessage(coded("unauthenticated"), "test")).toContain("expired");
    expect(providerErrorMessage(coded("invalid_token"), "load")).toContain("expired");
    expect(providerErrorMessage(coded("forbidden"), "delete")).toContain("don't have permission");
  });

  it("gives the test bucket its own rate-limit copy", () => {
    expect(providerErrorMessage(coded("rate_limited"), "test")).toContain(
      "Too many connection tests",
    );
    expect(providerErrorMessage(coded("rate_limited"), "create")).toContain("Too many requests");
  });

  it("maps the reserved live-provider codes (Stage 18 future-proofing)", () => {
    expect(providerErrorMessage(coded("provider_error"), "test")).toContain("couldn't be reached");
    expect(providerErrorMessage(coded("ai_unavailable"), "test")).toContain("couldn't be reached");
  });

  it("passes client codes through (safe by construction)", () => {
    const timeout = new ApiRequestError(0, {
      code: "request_timeout",
      message: "The request timed out. Please try again.",
    });
    expect(providerErrorMessage(timeout, "test")).toBe("The request timed out. Please try again.");
  });
});

describe("provider field errors", () => {
  it("maps known validation_error details onto fields", () => {
    const err = coded("validation_error", [
      { loc: ["body", "api_key"], msg: "String too short" },
      { loc: ["body", "label"], msg: "String too long" },
    ]);
    expect(providerFieldErrors(err)).toEqual({
      api_key: "Enter an API key between 4 and 2,000 characters.",
      label: "Keep the label under 80 characters.",
    });
  });

  it("ignores unknown fields, shapes, and non-validation errors", () => {
    const unknown = coded("validation_error", [{ loc: ["body", "mystery"], msg: "?" }]);
    expect(providerFieldErrors(unknown)).toEqual({});
    expect(providerFieldErrors(coded("validation_error", "garbage"))).toEqual({});
    expect(providerFieldErrors(coded("conflict"))).toEqual({});
    expect(providerFieldErrors(new Error("boom"))).toEqual({});
  });
});
