/**
 * Auth API layer — the ONLY module that talks to `/auth/*`. Built exclusively on
 * the canonical client (`lib/api.ts`): cookies flow via `credentials: "include"`
 * and session tokens never touch JS. Public auth actions use the same API client; session tokens stay in httpOnly cookies.
 */

import { api, ApiRequestError } from "./api";
import type {
  AuthSession,
  ChangePasswordInput,
  EmptyResponse,
  ForgotPasswordInput,
  LoginInput,
  RegisterInput,
  ResetPasswordInput,
  User,
} from "../types/auth";

/**
 * Where successful auth lands. TEMPORARY until the dashboard stage: a fixed
 * allowlist entry (the project contract), never a `?next=` parameter.
 */
export const AUTH_LANDING_PATH = "/dashboard";

export async function register(input: RegisterInput): Promise<AuthSession> {
  return api<AuthSession>("/auth/register", {
    method: "POST",
    body: {
      name: input.name,
      email: input.email,
      password: input.password,
    },
  });
}

export async function login(input: LoginInput): Promise<AuthSession> {
  return api<AuthSession>("/auth/login", {
    method: "POST",
    body: { email: input.email, password: input.password },
  });
}

export async function logout(): Promise<void> {
  await api<void>("/auth/logout", { method: "POST" });
}

/** Raw refresh — NEVER retry-wrap this (a 401 here means "signed out", not "retry"). */
export async function refreshSession(): Promise<AuthSession> {
  return api<AuthSession>("/auth/refresh", { method: "POST" });
}

export async function requestPasswordReset(input: ForgotPasswordInput): Promise<EmptyResponse> {
  return api<EmptyResponse>("/auth/forgot-password", {
    method: "POST",
    body: { email: input.email },
  });
}

export async function resetPassword(input: ResetPasswordInput): Promise<EmptyResponse> {
  return api<EmptyResponse>("/auth/reset-password", {
    method: "POST",
    body: {
      token: input.token,
      new_password: input.new_password,
    },
  });
}

// ---------------------------------------------------------------------------
// Silent refresh: single-flight + retry-once. Exactly one refresh request is
// ever in flight (concurrent expiries share it); a failed refresh resolves to
// "signed out" instead of looping. Applies ONLY to session reads/writes below:
// login/register/reset/logout each define their own 401 semantics and
// must surface them directly.
// ---------------------------------------------------------------------------

let refreshInflight: Promise<AuthSession> | null = null;

function refreshOnce(): Promise<AuthSession> {
  if (!refreshInflight) {
    refreshInflight = refreshSession().finally(() => {
      refreshInflight = null;
    });
  }
  return refreshInflight;
}

/**
 * Run `fn`, refreshing the session once on a 401 and retrying a single time.
 * Safe ONLY for reads and for mutations the server rejects pre-execution on
 * 401 (proven for `me`/`change-password`; Stage 06 extends it to analysis
 * creation, whose guard rejects before the service runs — no double-create).
 */
export async function withSessionRetry<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof ApiRequestError && err.code === "unauthenticated") {
      try {
        await refreshOnce();
      } catch {
        // Refresh failed (revoked/expired session) — the session is gone, so
        // the original 401 stands and the caller resolves to "signed out".
        throw err;
      }
      // Single retry: a second 401 (e.g. deleted mid-flight) propagates, no loop.
      return await fn();
    }
    throw err;
  }
}

/** Current identity with silent refresh — the AuthProvider init + refresh path. */
export async function getCurrentUser(): Promise<User> {
  return withSessionRetry(() => api<User>("/auth/me"));
}

/** Password change with silent refresh (a stale tab shouldn't fail this form). */
export async function changePassword(input: ChangePasswordInput): Promise<EmptyResponse> {
  return withSessionRetry(() =>
    api<EmptyResponse>("/auth/change-password", {
      method: "POST",
      body: { current_password: input.current_password, new_password: input.new_password },
    }),
  );
}

/**
 * Delete the signed-in account (contract §4.2: `{confirmation: "DELETE"}` →
 * 204 + cleared session cookies). Retry-safe like `changePassword`: the
 * guard rejects pre-execution on 401, and a deleted-then-retried account
 * reads 401 again (never a double delete — there is nothing left to delete).
 */
export async function deleteAccount(): Promise<void> {
  return withSessionRetry(() =>
    api<void>("/auth/account", { method: "DELETE", body: { confirmation: "DELETE" } }),
  );
}

/** True when the backend says "no usable session" (logged out / expired / revoked). */
export function isSessionGone(err: unknown): boolean {
  return (
    err instanceof ApiRequestError &&
    (err.code === "unauthenticated" || err.code === "invalid_token")
  );
}
