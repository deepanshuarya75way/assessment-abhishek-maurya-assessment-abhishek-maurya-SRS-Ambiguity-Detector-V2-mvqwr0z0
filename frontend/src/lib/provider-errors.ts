/**
 * Provider error-code → user-facing copy (the project contract: the frontend
 * switches on `code`, NEVER on `message`). Server strings are never displayed —
 * every branch below is our own copy, so backend wording can evolve freely.
 * `conflict` copy depends on the action (same code, different contradictions),
 * so callers pass their context; field-detail traversal is shared with
 * `lib/auth-errors.ts` (no duplication).
 */

import { ApiRequestError } from "./api";
import { validationFieldErrors, type ValidationFieldTable } from "./auth-errors";

/** Which provider action failed — `conflict`/`rate_limited` copy depends on it. */
export type ProviderErrorContext = "load" | "create" | "test" | "rotate" | "update" | "delete";

const GENERIC_FALLBACK = "Something went wrong. Please try again.";

function conflictMessage(context: ProviderErrorContext): string {
  switch (context) {
    case "create":
      return "A conflicting credential already exists for this provider. Replace the existing key, or disable that credential first.";
    case "rotate":
      return "That key is already stored on another credential.";
    case "update":
      return "That change conflicts with another credential. It may be disabled, or another credential may already be enabled for this provider — refresh the list and try again.";
    default:
      return "That change conflicts with another credential. Refresh the list and try again.";
  }
}

export function providerErrorMessage(err: unknown, context: ProviderErrorContext): string {
  if (!(err instanceof ApiRequestError)) return GENERIC_FALLBACK;
  switch (err.code) {
    case "ai_provider_not_found":
      return "That credential doesn't exist or belongs to a different account.";
    case "conflict":
      return conflictMessage(context);
    case "validation_error":
      return "Please check the highlighted fields and try again.";
    case "unauthenticated":
    case "invalid_token":
      return "Your session has expired. Please sign in again.";
    case "rate_limited":
      return context === "test"
        ? "Too many connection tests. Please wait a minute and try again."
        : "Too many requests. Please wait a moment and try again.";
    case "forbidden":
      return "You don't have permission to do that.";
    case "provider_error":
    case "ai_unavailable":
      // Live-provider codes (contract §4.6): creation/test/rotate can surface
      // provider reachability or validation failures with stable safe copy.
      return "The provider couldn't be reached. Try again later.";
    case "network_unreachable":
    case "request_timeout":
    case "bad_response":
      // Our own client's codes — messages are safe by construction (lib/api.ts).
      return err.message;
    default:
      return GENERIC_FALLBACK;
  }
}

/** Backend field names the provider forms map `validation_error` details onto. */
const PROVIDER_FIELDS: ValidationFieldTable = {
  known: new Set(["provider", "label", "api_key", "fallback_rank"]),
  copy: {
    provider: "Choose a supported provider.",
    label: "Keep the label under 80 characters.",
    api_key: "Enter an API key between 4 and 2,000 characters.",
    fallback_rank: "Rank must be between 0 and 32,767.",
  },
};

/**
 * Extract per-field errors from a provider `validation_error` envelope.
 * Unknown shapes → {} (same contract as the auth/analysis variants).
 */
export function providerFieldErrors(err: unknown): Partial<Record<string, string>> {
  return validationFieldErrors(err, PROVIDER_FIELDS);
}
