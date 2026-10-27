import { describe, expect, it } from "vitest";

import { ApiRequestError } from "./api";
import { authErrorMessage, validationFieldErrors, type AuthErrorContext } from "./auth-errors";

function serverError(code: string): ApiRequestError {
  // Server wording must NEVER leak through — every message here is a canary.
  return new ApiRequestError(400, { code, message: `SERVER SAYS ${code}` });
}

describe("authErrorMessage", () => {
  it.each([
    ["invalid_credentials", "login", "Invalid email or password."],
    ["account_disabled", "login", "This account has been disabled."],
    [
      "password_too_weak",
      "register",
      "This password doesn't meet our requirements — try something longer and less predictable.",
    ],
    ["current_password_incorrect", "change", "Current password is incorrect."],
    ["validation_error", "register", "Please check the highlighted fields and try again."],
    ["rate_limited", "login", "Too many attempts. Please try again later."],
    ["forbidden", "login", "You don't have permission to do that."],
    ["unauthenticated", "session", "Your session has expired. Please log in again."],
    ["something_new", "login", "Something went wrong. Please try again."],
  ] as Array<[string, AuthErrorContext, string]>)(
    "maps %s (in %s) to our own copy",
    (code, context, expected) => {
      expect(authErrorMessage(serverError(code), context)).toBe(expected);
    },
  );

  it.each([
    ["reset", "This reset link is invalid or has expired."],
    ["session", "Your session has expired. Please log in again."],
    ["login", "Your session has expired. Please log in again."],
    ["register", "This link is invalid or has expired."],
  ] as Array<[AuthErrorContext, string]>)(
    "maps invalid_token in %s context",
    (context, expected) => {
      expect(authErrorMessage(serverError("invalid_token"), context)).toBe(expected);
    },
  );

  it("passes through our own client's network/timeout messages", () => {
    const timeout = new ApiRequestError(0, {
      code: "request_timeout",
      message: "The request timed out. Please try again.",
    });
    expect(authErrorMessage(timeout, "login")).toBe("The request timed out. Please try again.");
  });

  it.each([[new Error("boom")], [null], [undefined], ["plain string"], [42]])(
    "falls back to generic copy for non-API errors (%s)",
    (err) => {
      expect(authErrorMessage(err, "login")).toBe("Something went wrong. Please try again.");
    },
  );
});

describe("validationFieldErrors", () => {
  function validationError(details: unknown): ApiRequestError {
    return new ApiRequestError(400, {
      code: "validation_error",
      message: "Request validation failed.",
      details,
    });
  }

  it("maps known field locators to our own copy", () => {
    const err = validationError([
      { loc: ["body", "email"], msg: "value is not a valid email address" },
      { loc: ["body", "password"], msg: "String should have at least 12 characters" },
    ]);
    expect(validationFieldErrors(err)).toEqual({
      email: "Enter a valid email address.",
      password: "Use at least 12 characters.",
    });
  });

  it("ignores unknown fields", () => {
    const err = validationError([{ loc: ["body", "future_field"], msg: "nope" }]);
    expect(validationFieldErrors(err)).toEqual({});
  });

  it("returns {} for non-validation errors", () => {
    expect(validationFieldErrors(serverError("invalid_token"))).toEqual({});
  });

  it("returns {} for malformed details", () => {
    expect(validationFieldErrors(validationError(null))).toEqual({});
    expect(validationFieldErrors(validationError("oops"))).toEqual({});
    expect(validationFieldErrors(validationError([null, 42, { nope: true }]))).toEqual({});
    expect(validationFieldErrors(validationError([{ loc: ["body", 3], msg: "x" }]))).toEqual({});
  });
});
