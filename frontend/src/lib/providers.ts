/**
 * Provider credential API layer — the ONLY module that talks to
 * `/ai/providers` (contract §4.6). Built exclusively on the canonical
 * client (`lib/api.ts`): cookies flow via `credentials: "include"` and
 * session tokens never touch JS. Every call rides `withSessionRetry`
 * (single-flight silent refresh + one retry), exactly like the analysis
 * and password-change calls. The browser NEVER contacts providers
 * directly — plaintext keys travel only to our backend, and only in
 * create/rotate request bodies that are never logged or persisted.
 */

import type {
  ProviderCreateInput,
  ProviderCredential,
  ProviderRotateInput,
  ProviderTestResult,
  ProviderUpdateInput,
} from "@/types/providers";

import { api } from "./api";
import { withSessionRetry } from "./auth";

/** Owned credentials, server-ordered (registry → enabled-first → oldest). */
export async function listProviders(): Promise<ProviderCredential[]> {
  return withSessionRetry(() => api<ProviderCredential[]>("/ai/providers"));
}

/** Store a credential (server forces enabled, never default). */
export async function createProvider(input: ProviderCreateInput): Promise<ProviderCredential> {
  return withSessionRetry(() =>
    api<ProviderCredential>("/ai/providers", { method: "POST", body: input }),
  );
}

/** Update metadata (label / enabled / default / rank). */
export async function updateProvider(
  id: string,
  input: ProviderUpdateInput,
): Promise<ProviderCredential> {
  return withSessionRetry(() =>
    api<ProviderCredential>(`/ai/providers/${id}`, { method: "PATCH", body: input }),
  );
}

/** Replace stored key material (server clears the previous test verdict). */
export async function rotateProviderKey(
  id: string,
  input: ProviderRotateInput,
): Promise<ProviderCredential> {
  return withSessionRetry(() =>
    api<ProviderCredential>(`/ai/providers/${id}/rotate-key`, {
      method: "POST",
      body: input,
    }),
  );
}

/**
 * Live-check a STORED credential (there is no unsaved-key test endpoint —
 * the dialog never offers one). Always 200: read `ok`, not the status.
 */
export async function testProvider(id: string): Promise<ProviderTestResult> {
  return withSessionRetry(() =>
    api<ProviderTestResult>(`/ai/providers/${id}/test`, { method: "POST" }),
  );
}

/** Delete a credential (204 — ciphertext gone, nothing retained). */
export async function deleteProvider(id: string): Promise<void> {
  return withSessionRetry(() => api<void>(`/ai/providers/${id}`, { method: "DELETE" }));
}
