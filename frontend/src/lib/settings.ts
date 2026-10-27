/**
 * Settings API layer — the ONLY module that talks to `/settings/*`. Built on
 * the canonical client (`lib/api.ts`) with `withSessionRetry`: the verified
 * guard rejects pre-execution on 401, so the single retry can never
 * double-apply a profile write (and reads are idempotent by nature).
 */

import type { Profile, UpdateProfileInput } from "../types/settings";

import { api } from "./api";
import { withSessionRetry } from "./auth";

export async function getProfile(): Promise<Profile> {
  return withSessionRetry(() => api<Profile>("/settings/profile"));
}

export async function updateProfile(input: UpdateProfileInput): Promise<Profile> {
  return withSessionRetry(() =>
    api<Profile>("/settings/profile", {
      method: "PATCH",
      body: { display_name: input.display_name },
    }),
  );
}
