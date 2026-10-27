import type { ErrorEvent, EventHint } from "@sentry/nextjs";
import * as Sentry from "@sentry/nextjs";

const FILTERED = "[Filtered]";
const MAX_STRING_CHARS = 512;

const SENSITIVE_KEY_PARTS = [
  "authorization",
  "cookie",
  "password",
  "passwd",
  "pwd",
  "secret",
  "token",
  "csrf",
  "api_key",
  "apikey",
  "credential",
  "prompt",
  "response",
  "source_text",
  "requirement_text",
  "document_content",
  "file",
  "storage_path",
];

function isSensitiveKey(key: string): boolean {
  const normalized = key.toLowerCase().replaceAll("-", "_");
  return SENSITIVE_KEY_PARTS.some((part) => normalized.includes(part));
}

function truncate(value: string): string {
  if (value.length <= MAX_STRING_CHARS) return value;
  return `${value.slice(0, MAX_STRING_CHARS)}…[truncated]`;
}

function stripQuery(url: string): string {
  try {
    const parsed = new URL(url, "http://placeholder.local");
    parsed.search = "";
    parsed.hash = "";
    return url.startsWith("http") ? parsed.toString() : parsed.pathname;
  } catch {
    return FILTERED;
  }
}

export function scrubMonitoringValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.slice(0, 50).map(scrubMonitoringValue);
  if (value !== null && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      output[key] = isSensitiveKey(key) ? FILTERED : scrubMonitoringValue(child);
    }
    return output;
  }
  if (typeof value === "string") return truncate(value);
  return value;
}

export function sentryBeforeSend(event: ErrorEvent, hint: EventHint): ErrorEvent | null {
  void hint;
  const request = event.request as Record<string, unknown> | undefined;
  if (request !== undefined) {
    if (typeof request.url === "string") request.url = stripQuery(request.url);
    request.query_string = FILTERED;
    request.data = FILTERED;
    request.cookies = FILTERED;
    if (request.headers !== undefined) request.headers = scrubMonitoringValue(request.headers);
    event.request = request;
  }
  event.extra = scrubMonitoringValue(event.extra) as ErrorEvent["extra"];
  event.contexts = scrubMonitoringValue(event.contexts) as ErrorEvent["contexts"];
  event.breadcrumbs = scrubMonitoringValue(event.breadcrumbs) as ErrorEvent["breadcrumbs"];

  if (event.exception?.values !== undefined) {
    event.exception.values = event.exception.values.map((item) => ({
      ...item,
      value: item.value === undefined ? undefined : "details redacted",
    }));
  }
  if (event.message !== undefined) event.message = truncate(event.message);
  return event;
}

export function initFrontendMonitoring(): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    tracesSampleRate: 0,
    beforeSend: sentryBeforeSend,
  });
}

export function reportRouteError(error: Error & { digest?: string }): void {
  if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return;
  Sentry.captureException(error, {
    tags: { component: "next_route_error" },
    extra: error.digest ? { digest: error.digest } : undefined,
  });
}
