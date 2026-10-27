/**
 * Provider credential types — mirror the project contract exactly.
 * The ONLY key-derived value the backend ever sends is `masked_key`
 * (12 bullets + last4): the frontend can never reconstruct, display, or
 * resubmit a stored secret — replacement always starts from a blank field.
 */

/** Canonical provider vocabulary (contract §4.6, registry order — the list order). */
export const PROVIDER_IDS = [
  "gemini",
  "groq",
  "openai",
  "anthropic",
  "openrouter",
  "huggingface",
] as const;

export type ProviderId = (typeof PROVIDER_IDS)[number];

/**
 * Human-friendly display names — the SINGLE presentation mapping (the API
 * returns stable machine ids only, so this table is required, not duplicated).
 */
export const PROVIDER_DISPLAY_NAMES: Record<ProviderId, string> = {
  gemini: "Google Gemini",
  groq: "Groq",
  openai: "OpenAI",
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  huggingface: "Hugging Face",
};

export function isProviderId(value: unknown): value is ProviderId {
  return typeof value === "string" && (PROVIDER_IDS as readonly string[]).includes(value);
}

/** GET/POST/PATCH/rotate shapes — safe metadata only, never the key. */
export interface ProviderCredential {
  id: string;
  provider: ProviderId;
  label: string | null;
  masked_key: string;
  is_enabled: boolean;
  is_default: boolean;
  fallback_rank: number;
  key_version: number;
  last_tested_at: string | null;
  last_test_status: "ok" | "failed" | null;
}

/**
 * POST …/test verdict (always 200: a failed check is data, not an error).
 * `error` is backend-curated, user-safe text (contract §4.6) — the one
 * backend string the UI renders verbatim, capped server-side at 300 chars.
 */
export interface ProviderTestResult {
  ok: boolean;
  models: string[];
  latency_ms: number;
  error: string | null;
}

export interface ProviderCreateInput {
  provider: ProviderId;
  label?: string | null;
  api_key: string;
}

export interface ProviderUpdateInput {
  label?: string | null;
  is_enabled?: boolean;
  is_default?: boolean;
  fallback_rank?: number;
}

export interface ProviderRotateInput {
  api_key: string;
}
