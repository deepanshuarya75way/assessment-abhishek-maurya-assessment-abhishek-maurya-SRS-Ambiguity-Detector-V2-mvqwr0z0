/**
 * Settings error-code → user-facing copy (the project contract: the frontend
 * switches on `code`, NEVER on `message`). Server strings are never displayed.
 * Mirrors `lib/provider-errors.ts` for the profile load/save contexts.
 */

import { ApiRequestError } from "./api";

/** Which settings action failed — `validation_error` copy depends on it. */
export type SettingsErrorContext = "load" | "save";

const GENERIC_FALLBACK = "Something went wrong. Please try again.";

export function settingsErrorMessage(err: unknown, context: SettingsErrorContext): string {
  if (!(err instanceof ApiRequestError)) return GENERIC_FALLBACK;
  switch (err.code) {
    case "validation_error":
      return context === "save"
        ? "That name can't be saved — keep it under 100 characters."
        : GENERIC_FALLBACK;
    case "unauthenticated":
    case "invalid_token":
      return "Your session has expired. Please sign in again.";
    case "rate_limited":
      return "Too many requests. Please wait a moment and try again.";
    case "forbidden":
      return "You don't have permission to do that.";
    default:
      return GENERIC_FALLBACK;
  }
}
