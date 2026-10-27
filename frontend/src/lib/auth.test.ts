import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "./api";
import {
  changePassword,
  getCurrentUser,
  isSessionGone,
  login,
  logout,
  refreshSession,
  register,
  requestPasswordReset,
  resetPassword,
} from "./auth";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `server ${code}` } }, status);
}

const USER = {
  id: "u1",
  email: "ada@example.com",
  display_name: "Ada",
  is_verified: true,
  is_active: true,
  created_at: "2026-09-24T00:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("auth api layer", () => {
  it("registers with exactly name/email/password", async () => {
    const inits: Array<RequestInit | undefined> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      inits.push(init);
      return jsonResponse({ id: "u1", email: "ada@example.com", is_verified: false });
    });
    vi.stubGlobal("fetch", fetchMock);
    await register({ name: "Ada", email: "ada@example.com", password: "long-enough-1" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(inits).toHaveLength(1);
    const init = inits[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      name: "Ada",
      email: "ada@example.com",
      password: "long-enough-1",
    });
  });

  it("logs in with email/password only", async () => {
    const inits: Array<RequestInit | undefined> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        inits.push(init);
        return jsonResponse({ id: "u1", email: "ada@example.com", is_verified: true });
      }),
    );
    await login({ email: "ada@example.com", password: "long-enough-1" });
    expect(inits).toHaveLength(1);
    expect(JSON.parse(String(inits[0]?.body))).toEqual({
      email: "ada@example.com",
      password: "long-enough-1",
    });
  });

  it("sends only auth fields for register, login, forgot, and reset", async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)));
      return jsonResponse({});
    }));
    await register({ name: "Ada", email: "ada@example.com", password: "long-enough-1" });
    await login({ email: "ada@example.com", password: "long-enough-1" });
    await requestPasswordReset({ email: "a@b.co" });
    await resetPassword({ token: "tok", new_password: "new-password-12" });
    expect(bodies).toEqual([
      { name: "Ada", email: "ada@example.com", password: "long-enough-1" },
      { email: "ada@example.com", password: "long-enough-1" },
      { email: "a@b.co" },
      { token: "tok", new_password: "new-password-12" },
    ]);
  });

  it("resolves undefined on logout 204", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    await expect(logout()).resolves.toBeUndefined();
  });

  it("sends email payloads for forgot/reset", async () => {
    const urls: string[] = [];
    const bodies: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      urls.push(String(input));
      bodies.push(JSON.parse(String(init?.body)));
      return jsonResponse({});
    }));
    await requestPasswordReset({ email: "a@b.co" });
    await resetPassword({ token: "tok", new_password: "new-password-12" });
    expect(urls).toEqual([
      expect.stringContaining("/auth/forgot-password"),
      expect.stringContaining("/auth/reset-password"),
    ]);
    expect(bodies).toEqual([
      { email: "a@b.co" },
      { token: "tok", new_password: "new-password-12" },
    ]);
  });

  it("passes /me through on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(USER)),
    );
    await expect(getCurrentUser()).resolves.toEqual(USER);
  });

  it("silently refreshes once on 401, then retries", async () => {
    const paths: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        paths.push(url);
        if (url.includes("/auth/refresh")) {
          return jsonResponse({ id: "u1", email: "ada@example.com", is_verified: true });
        }
        if (paths.filter((p) => p.includes("/auth/me")).length === 1) {
          return envelope("unauthenticated", 401);
        }
        return jsonResponse(USER);
      }),
    );
    await expect(getCurrentUser()).resolves.toEqual(USER);
    expect(paths.filter((p) => p.includes("/auth/me"))).toHaveLength(2);
    expect(paths.filter((p) => p.includes("/auth/refresh"))).toHaveLength(1);
  });

  it("rethows the ORIGINAL 401 when refresh fails (no loop, no masking)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/auth/refresh")
          ? envelope("invalid_token", 400)
          : envelope("unauthenticated", 401),
      ),
    );
    const err = await getCurrentUser().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as ApiRequestError).code).toBe("unauthenticated");
    expect((err as ApiRequestError).status).toBe(401);
  });

  it("does not retry non-401 failures", async () => {
    const fetchMock = vi.fn(async () => envelope("email_unverified", 403));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getCurrentUser()).rejects.toMatchObject({ code: "email_unverified" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shares one in-flight refresh across concurrent expiries", async () => {
    let refreshCalls = 0;
    let meCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/refresh")) {
          refreshCalls += 1;
          await new Promise((r) => setTimeout(r, 10));
          return jsonResponse({ id: "u1", email: "a@b.co", is_verified: true });
        }
        meCalls += 1;
        return meCalls <= 2 ? envelope("unauthenticated", 401) : jsonResponse(USER);
      }),
    );
    const [a, b] = await Promise.all([getCurrentUser(), getCurrentUser()]);
    expect(a).toEqual(USER);
    expect(b).toEqual(USER);
    expect(refreshCalls).toBe(1);
  });

  it("retries change-password through a refresh", async () => {
    const paths: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        paths.push(url);
        if (url.includes("/auth/refresh")) {
          return jsonResponse({ id: "u1", email: "a@b.co", is_verified: true });
        }
        if (paths.filter((p) => p.includes("change-password")).length === 1) {
          return envelope("unauthenticated", 401);
        }
        return jsonResponse({});
      }),
    );
    await expect(
      changePassword({ current_password: "old-password-12", new_password: "new-password-12" }),
    ).resolves.toEqual({});
    expect(paths.filter((p) => p.includes("/auth/refresh"))).toHaveLength(1);
  });

  it("exposes a raw refresh (never retry-wrapped)", async () => {
    const fetchMock = vi.fn(async () => envelope("invalid_token", 400));
    vi.stubGlobal("fetch", fetchMock);
    await expect(refreshSession()).rejects.toMatchObject({ code: "invalid_token" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("isSessionGone only matches logged-out shapes", () => {
    expect(isSessionGone(new ApiRequestError(401, { code: "unauthenticated", message: "x" }))).toBe(
      true,
    );
    expect(isSessionGone(new ApiRequestError(400, { code: "invalid_token", message: "x" }))).toBe(
      true,
    );
    expect(
      isSessionGone(new ApiRequestError(403, { code: "email_unverified", message: "x" })),
    ).toBe(false);
    expect(isSessionGone(new Error("net down"))).toBe(false);
    expect(isSessionGone(null)).toBe(false);
  });
});
