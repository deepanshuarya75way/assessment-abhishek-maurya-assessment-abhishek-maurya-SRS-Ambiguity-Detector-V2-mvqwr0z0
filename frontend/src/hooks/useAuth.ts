"use client";

/** Access the AuthProvider context (status/user + login/signup/logout/...). */

import { useContext } from "react";

import { AuthContext, type AuthContextValue } from "@/components/auth/AuthProvider";

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
