/**
 * Report-only Content Security Policy (the project contract).
 *
 * Served as `Content-Security-Policy-Report-Only` in production only: violations
 * are observed (console) without breaking the app, so the policy can be tuned
 * from real-browser data before any future enforce-mode rollout. The only
 * cross-origin allowance is the API origin the SPA fetches (env-configured);
 * everything else is same-origin or stricter.
 */

const DEFAULT_API_URL = "http://localhost:8000/api/v1";

/** Extract the fetchable origin from an API base URL; falls back to 'self'. */
export function apiOrigin(apiUrl: string | undefined): string {
  try {
    return new URL(apiUrl ?? DEFAULT_API_URL).origin;
  } catch {
    return "'self'";
  }
}

/** Build the report-only policy value for the given API base URL. */
export function buildReportOnlyCsp(apiUrl: string | undefined): string {
  return [
    "default-src 'self'",
    // Next's inline runtime requires 'unsafe-inline' without nonce plumbing;
    // report-only lets us confirm nothing else needs script-src before enforcing.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    // Fonts are self-hosted (Fontsource) — no external font-src needed.
    "font-src 'self'",
    `connect-src 'self' ${apiOrigin(apiUrl)}`,
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
  ].join("; ");
}
