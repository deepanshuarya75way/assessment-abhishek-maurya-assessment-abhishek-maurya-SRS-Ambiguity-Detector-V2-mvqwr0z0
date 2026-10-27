/**
 * Auth domain types — mirrored from the project contract
 * (backend: `app/schemas/auth.py`). Same names, same optionality.
 * Sessions ride httpOnly cookies; these shapes carry identity only, never tokens.
 */

/** GET /auth/me — safe identity subset (never hashes/tokens/keys). */
export interface User {
  id: string;
  email: string;
  display_name: string | null;
  is_verified: boolean;
  is_active: boolean;
  created_at: string;
}

/**
 * POST register/login/refresh — session proof, cookies do the work.
 */
export interface AuthSession {
  id: string;
  email: string;
  is_verified: boolean;
}

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface ForgotPasswordInput {
  email: string;
}

export interface ResetPasswordInput {
  token: string;
  new_password: string;
}

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}

/** Empty-object success bodies (`202 {}` / `200 {}`) — key presence is meaningless. */
export type EmptyResponse = Record<string, never>;

/** AuthProvider resolution state — the single source of auth truth. */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthState {
  status: AuthStatus;
  /** Non-null if and only if `status === "authenticated"`. */
  user: User | null;
}
