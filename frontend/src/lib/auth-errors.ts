/**
 * Backend error-code → user-facing copy (the project contract: the frontend
 * switches on `code`, NEVER on `message`). Server strings are never displayed —
 * every branch below is our own copy, so backend wording can evolve freely.
 * Anti-enumeration responses (synthetic-201 / always-202) need no mapping:
 * they arrive as successes by design.
 */

import { ApiRequestError } from "./api";

/** Which flow failed — `invalid_token` copy depends on it. */
export type AuthErrorContext =
  "login" | "register" | "forgot" | "reset" | "change" | "session";

const GENERIC_FALLBACK = "Something went wrong. Please try again.";

function invalidTokenMessage(context: AuthErrorContext): string {
  switch (context) {
    case "reset":
      return "This reset link is invalid or has expired.";
    case "session":
    case "login":
      return "Your session has expired. Please log in again.";
    default:
      return "This link is invalid or has expired.";
  }
}

export function authErrorMessage(err: unknown, context: AuthErrorContext): string {
  if (!(err instanceof ApiRequestError)) return GENERIC_FALLBACK;
  switch (err.code) {
    case "invalid_credentials":
      return "Invalid email or password.";
    case "account_disabled":
      return "This account has been disabled.";
    case "invalid_token":
      return invalidTokenMessage(context);
    case "password_too_weak":
      return "This password doesn't meet our requirements — try something longer and less predictable.";
    case "current_password_incorrect":
      return "Current password is incorrect.";
    case "validation_error":
      return "Please check the highlighted fields and try again.";
    case "rate_limited":
      return "Too many attempts. Please try again later.";
    case "forbidden":
      return "You don't have permission to do that.";
    case "unauthenticated":
      return "Your session has expired. Please log in again.";
    case "network_unreachable":
    case "request_timeout":
    case "bad_response":
      // Our own client's codes — messages are safe by construction (lib/api.ts).
      return err.message;
    default:
      return GENERIC_FALLBACK;
  }
}

/** Backend field names we map `validation_error` details onto (loc tail match). */
const KNOWN_FIELDS = new Set([
  "name",
  "email",
  "password",
  "new_password",
  "current_password",
  "token",
  "confirmation",
]);

const FIELD_COPY: Record<string, string> = {
  name: "Enter your name (up to 100 characters).",
  email: "Enter a valid email address.",
  password: "Use at least 12 characters.",
  new_password: "Use at least 12 characters.",
  current_password: "Enter your current password.",
  token: "This link looks incomplete — request a new one.",
  confirmation: "Type DELETE to confirm.",
};

interface ValidationDetail {
  loc: unknown[];
  msg: string;
}

function isValidationDetail(value: unknown): value is ValidationDetail {
  if (typeof value !== "object" || value === null) return false;
  const detail = value as { loc?: unknown; msg?: unknown };
  return Array.isArray(detail.loc) && typeof detail.msg === "string";
}

/** Field table a domain maps `validation_error` details onto. */
export interface ValidationFieldTable {
  known: Set<string>;
  copy: Record<string, string>;
}

const AUTH_FIELD_TABLE: ValidationFieldTable = { known: KNOWN_FIELDS, copy: FIELD_COPY };

/**
 * Extract per-field errors from a `validation_error` envelope
 * (`details: [{loc: [...], msg}]` — backend main.py). Unknown shapes → {}.
 * Copy is ours; server `msg` strings are never displayed. Other domains pass
 * their own table (Stage 06: the analyzer) instead of duplicating this walk.
 */
export function validationFieldErrors(
  err: unknown,
  table: ValidationFieldTable = AUTH_FIELD_TABLE,
): Partial<Record<string, string>> {
  if (!(err instanceof ApiRequestError) || err.code !== "validation_error") return {};
  if (!Array.isArray(err.details)) return {};
  const fields: Partial<Record<string, string>> = {};
  for (const detail of err.details) {
    if (!isValidationDetail(detail)) continue;
    const tail = detail.loc[detail.loc.length - 1];
    if (typeof tail === "string" && table.known.has(tail) && fields[tail] === undefined) {
      const copy = table.copy[tail];
      if (copy !== undefined) fields[tail] = copy;
    }
  }
  return fields;
}
