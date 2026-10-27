"use client";

/**
 * AuthProvider — the single source of auth truth (status/user + actions).
 * Identity resolves once via GET /auth/me (one request even under StrictMode's
 * dev double-effect, via the module-level init guard); tokens stay in httpOnly
 * cookies and are never read here. Local state only ever mirrors the backend.
 */

import { createContext, useCallback, useEffect, useMemo, useState } from "react";

import {
  getCurrentUser,
  isSessionGone,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from "@/lib/auth";
import type { AuthSession, AuthState, LoginInput, RegisterInput, User } from "@/types/auth";

export interface AuthContextValue extends AuthState {
  /** Sign in, then load the full identity. Throws ApiRequestError on failure. */
  login: (input: LoginInput) => Promise<AuthSession>;
  /** Register — never logs in (contract §4.2), so identity is left untouched. */
  signup: (input: RegisterInput) => Promise<AuthSession>;
  /**
   * Sign out. Clears local state on success AND when the session is already
   * gone server-side; rethrows network/timeout errors WITHOUT clearing (a
   * failed request must not fake a logout).
   */
  logout: () => Promise<void>;
  /**
   * Re-resolve identity from the backend. Never throws: unresolvable identity
   * (logged out, expired, network down) resolves to `null` + `unauthenticated`
   * state, because a failed read must never leave the app in a lying state.
   */
  refreshUser: () => Promise<User | null>;
  /** Synchronous escape hatch — drop local identity without any request. */
  clearAuth: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** One in-flight init request, shared even across StrictMode's dev remount. */
let initInflight: Promise<User | null> | null = null;

async function loadUser(): Promise<User | null> {
  try {
    return await getCurrentUser();
  } catch {
    return null;
  }
}

function loadInitialUser(): Promise<User | null> {
  if (!initInflight) {
    initInflight = loadUser().finally(() => {
      initInflight = null;
    });
  }
  return initInflight;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  useEffect(() => {
    let cancelled = false;
    void loadInitialUser().then((user) => {
      if (cancelled) return;
      setState(
        user === null
          ? { status: "unauthenticated", user: null }
          : { status: "authenticated", user },
      );
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshUser = useCallback(async (): Promise<User | null> => {
    const user = await loadUser();
    setState(
      user === null ? { status: "unauthenticated", user: null } : { status: "authenticated", user },
    );
    return user;
  }, []);

  const clearAuth = useCallback((): void => {
    setState({ status: "unauthenticated", user: null });
  }, []);

  const login = useCallback(
    async (input: LoginInput): Promise<AuthSession> => {
      const session = await loginRequest(input);
      // Session cookies are set; confirm the full identity (a read blip here
      // leaves honest `unauthenticated` state that heals on next refresh).
      await refreshUser();
      return session;
    },
    [refreshUser],
  );

  // Registration starts a session immediately; resolve identity before navigation.
  const signup = useCallback(async (input: RegisterInput): Promise<AuthSession> => {
    const session = await registerRequest(input);
    await refreshUser();
    return session;
  }, [refreshUser]);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await logoutRequest();
    } catch (err) {
      if (!isSessionGone(err)) throw err;
      // Session already gone server-side — still a successful sign-out.
    }
    setState({ status: "unauthenticated", user: null });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status: state.status,
      user: state.user,
      login,
      signup,
      logout,
      refreshUser,
      clearAuth,
    }),
    [state.status, state.user, login, signup, logout, refreshUser, clearAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
