// @vitest-environment jsdom
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, act } from "@testing-library/react";

import type { AuthContextValue } from "./AuthProvider";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "@/hooks/useAuth";
import { ApiRequestError } from "@/lib/api";

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
  id: "user-1",
  email: "ada@example.com",
  display_name: "Ada",
  is_verified: false,
  is_active: true,
  created_at: "2026-09-24T00:00:00Z",
};

let captured: AuthContextValue | null = null;

function Harness() {
  const auth = useAuth();
  useEffect(() => {
    captured = auth;
  }, [auth]);
  return (
    <p data-testid="status">
      {auth.status}:{auth.user?.email ?? "none"}
    </p>
  );
}

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function loggedOutFetch() {
  return stubFetch((url) =>
    url.includes("/auth/me") ? envelope("unauthenticated", 401) : envelope("invalid_token", 400),
  );
}

afterEach(() => {
  cleanup();
  captured = null;
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AuthProvider", () => {
  it("resolves to unauthenticated when no session exists (me + one refresh)", async () => {
    const fetchMock = loggedOutFetch();
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    expect(screen.getByTestId("status").textContent).toBe("loading:none");
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none"),
    );
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      expect.stringContaining("/auth/me"),
      expect.stringContaining("/auth/refresh"),
    ]);
  });

  it("resolves to authenticated when a session exists", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return jsonResponse(USER);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com"),
    );
  });

  it("silently refreshes an expired session on init", async () => {
    let meCalls = 0;
    const fetchMock = stubFetch((url) => {
      if (url.includes("/auth/refresh")) {
        return jsonResponse({ id: "user-1", email: USER.email, is_verified: false });
      }
      meCalls += 1;
      return meCalls === 1 ? envelope("unauthenticated", 401) : jsonResponse(USER);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com"),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("login() sends credentials, loads identity, and reports failures honestly", async () => {
    const bodies: unknown[] = [];
    stubFetch((url, init) => {
      if (init?.body) bodies.push(JSON.parse(init.body as string));
      if (url.includes("/auth/login")) return envelope("invalid_credentials", 401);
      if (url.includes("/auth/me")) return envelope("unauthenticated", 401);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none"),
    );
    let thrown: unknown = null;
    await act(async () => {
      try {
        await captured?.login({ email: "ada@example.com", password: "wrong-password-1" });
      } catch (err) {
        thrown = err;
      }
    });
    expect(thrown).toBeInstanceOf(ApiRequestError);
    expect((thrown as ApiRequestError).code).toBe("invalid_credentials");
    expect(bodies).toContainEqual({ email: "ada@example.com", password: "wrong-password-1" });
    expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none");
  });

  it("logs out and clears state on 204", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/logout")) return new Response(null, { status: 204 });
      if (url.includes("/auth/me")) return jsonResponse(USER);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com"),
    );
    await act(async () => {
      await captured?.logout();
    });
    expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none");
  });

  it("logout() still clears when the session is already gone server-side", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/logout")) return envelope("unauthenticated", 401);
      if (url.includes("/auth/me")) return jsonResponse(USER);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com"),
    );
    await act(async () => {
      await captured?.logout();
    });
    expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none");
  });

  it("logout() rethrows network failures WITHOUT clearing (no fake logout)", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/logout")) throw new TypeError("fetch failed");
      if (url.includes("/auth/me")) return jsonResponse(USER);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com"),
    );
    let thrown: unknown = null;
    await act(async () => {
      try {
        await captured?.logout();
      } catch (err) {
        thrown = err;
      }
    });
    expect(thrown).toBeInstanceOf(ApiRequestError);
    expect((thrown as ApiRequestError).code).toBe("network_unreachable");
    expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com");
  });

  it("refreshUser() never throws — unresolvable identity becomes null", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) throw new TypeError("fetch failed");
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none"),
    );
    let result: unknown = "unset";
    await act(async () => {
      result = await captured?.refreshUser();
    });
    expect(result).toBeNull();
  });

  it("clearAuth() drops identity synchronously", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return jsonResponse(USER);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com"),
    );
    act(() => {
      captured?.clearAuth();
    });
    expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none");
  });

  it("signup() registers and resolves the new session", async () => {
    let registered = false;
    const fetchMock = stubFetch((url) => {
      if (url.includes("/auth/register")) {
        registered = true;
        return jsonResponse({ id: "user-1", email: USER.email, is_verified: true }, 201);
      }
      if (url.includes("/auth/me")) {
        return registered ? jsonResponse(USER) : envelope("unauthenticated", 401);
      }
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <Harness />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("unauthenticated:none"),
    );
    let session: unknown = null;
    await act(async () => {
      session = await captured?.signup({
        name: "Ada",
        email: "ada@example.com",
        password: "long-enough-1",
      });
    });
    expect(session).toEqual({ id: "user-1", email: USER.email, is_verified: true });
    expect(screen.getByTestId("status").textContent).toBe("authenticated:ada@example.com");
    // One initial identity read and one post-registration session read.
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/auth/register")),
    ).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/auth/me"))).toHaveLength(
      2,
    );
  });
});
