/**
 * Typed API client — the ONLY way feature code talks to the backend
 * (the project contract). Encodes the project contract envelopes:
 * success → resource/collection JSON; failure → ApiRequestError with `code`.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface Collection<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export class ApiRequestError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiRequestError";
    this.code = body.code;
    this.status = status;
    this.details = body.details ?? null;
  }
}

const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(
  /\/$/,
  "",
);

/** Default per-request timeout (ms). Long AI/document calls may override per call. */
export const DEFAULT_TIMEOUT_MS = 30_000;

interface ApiOptions extends Omit<RequestInit, "body" | "signal"> {
  body?: unknown;
  /** Per-request timeout in ms (default 30 000). `0` disables the timeout. */
  timeoutMs?: number;
}

function isErrorEnvelope(json: unknown): json is { error: ApiErrorBody } {
  if (typeof json !== "object" || json === null) return false;
  const err = (json as { error?: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as ApiErrorBody).code === "string" &&
    typeof (err as ApiErrorBody).message === "string"
  );
}

/**
 * Envelope decoding shared by `api` (JSON) and `apiForm` (multipart): 204 →
 * void, envelope failures → ApiRequestError, anything else → bad_response
 * (raw bodies — HTML error pages, … — are never surfaced).
 */
async function parseResponse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;

  let json: unknown = null;
  try {
    json = await res.json();
  } catch {
    // Non-JSON response (proxy/gateway error page, …) — never leak raw HTML.
    throw new ApiRequestError(res.status, {
      code: "bad_response",
      message: "The service returned an unexpected response.",
    });
  }

  if (!res.ok) {
    if (isErrorEnvelope(json)) throw new ApiRequestError(res.status, json.error);
    throw new ApiRequestError(res.status, {
      code: "bad_response",
      message: "The service returned an unexpected response.",
    });
  }
  return json as T;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { body, headers, timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = options;
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(headers ?? {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: timeoutMs > 0 ? AbortSignal.timeout(timeoutMs) : undefined,
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiRequestError(0, {
        code: "request_timeout",
        message: "The request timed out. Please try again.",
      });
    }
    throw new ApiRequestError(0, {
      code: "network_unreachable",
      message: "Could not reach the analysis service. Is the backend running?",
    });
  }

  return parseResponse<T>(res);
}

interface ApiFormOptions extends Omit<RequestInit, "body" | "headers" | "signal"> {
  /** Per-request timeout in ms (default 30 000). `0` disables the timeout. */
  timeoutMs?: number;
}

/**
 * Multipart sibling of `api` (file uploads): same envelopes, same client
 * codes — but the browser sets the multipart boundary itself, so no
 * Content-Type header is sent (setting one would break the boundary).
 */
export async function apiForm<T>(
  path: string,
  form: FormData,
  options: ApiFormOptions = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = options;
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      method: "POST",
      credentials: "include",
      body: form,
      signal: timeoutMs > 0 ? AbortSignal.timeout(timeoutMs) : undefined,
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiRequestError(0, {
        code: "request_timeout",
        message: "The request timed out. Please try again.",
      });
    }
    throw new ApiRequestError(0, {
      code: "network_unreachable",
      message: "Could not reach the analysis service. Is the backend running?",
    });
  }
  return parseResponse<T>(res);
}

/** Base URL (read-only) — for building links such as API docs. Never fetch directly. */
export function apiBaseUrl(): string {
  return BASE_URL;
}
