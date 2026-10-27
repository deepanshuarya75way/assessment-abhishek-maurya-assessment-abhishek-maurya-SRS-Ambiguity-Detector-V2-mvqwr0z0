// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";

import { AuthProvider } from "@/components/auth/AuthProvider";
import { useAuth } from "./useAuth";

function envelope(code: string, status: number): Response {
  return new Response(JSON.stringify({ error: { code, message: `server ${code}` } }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("useAuth", () => {
  it("throws outside the provider", () => {
    expect(() => renderHook(() => useAuth())).toThrow("useAuth must be used within <AuthProvider>");
  });

  it("exposes status, user, and actions inside the provider", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/auth/me")
          ? envelope("unauthenticated", 401)
          : envelope("invalid_token", 400),
      ),
    );
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }: { children: React.ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
      ),
    });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));
    expect(result.current.user).toBeNull();
    for (const action of ["login", "signup", "logout", "refreshUser", "clearAuth"] as const) {
      expect(typeof result.current[action]).toBe("function");
    }
  });
});
