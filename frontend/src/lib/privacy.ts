/** Privacy API layer — settings, export tickets, and history purge controls. */

import type {
  PrivacyExportTicket,
  PrivacyPurgeInput,
  PrivacyPurgeResult,
  PrivacySettings,
  UpdatePrivacySettingsInput,
} from "@/types/privacy";

import { api, apiBaseUrl } from "./api";
import { withSessionRetry } from "./auth";

export async function getPrivacySettings(): Promise<PrivacySettings> {
  return withSessionRetry(() => api<PrivacySettings>("/settings/privacy"));
}

export async function updatePrivacySettings(
  input: UpdatePrivacySettingsInput,
): Promise<PrivacySettings> {
  return withSessionRetry(() =>
    api<PrivacySettings>("/settings/privacy", {
      method: "PATCH",
      body: { history_retention_days: input.history_retention_days },
    }),
  );
}

export async function createPrivacyExport(): Promise<PrivacyExportTicket> {
  return withSessionRetry(() => api<PrivacyExportTicket>("/privacy/export", { method: "POST" }));
}

export async function purgeHistory(input: PrivacyPurgeInput): Promise<PrivacyPurgeResult> {
  return withSessionRetry(() =>
    api<PrivacyPurgeResult>("/privacy/purge-history", {
      method: "POST",
      body: input,
    }),
  );
}

export function apiDownloadUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl().replace(/\/api\/v1$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}
