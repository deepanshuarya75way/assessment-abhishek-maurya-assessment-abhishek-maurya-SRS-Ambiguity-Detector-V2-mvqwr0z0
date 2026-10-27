// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { AuthProvider } from "./AuthProvider";
import { ProtectedRoute } from "./ProtectedRoute";

const nav = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: nav.replace,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `server ${code}` } }, status);
}

function userResponse(verified: boolean) {
  return jsonResponse({
    id: "user-1",
    email: "ada@example.com",
    display_name: "Ada",
    is_verified: verified,
    is_active: true,
    created_at: "2026-09-24T00:00:00Z",
  });
}

function stubFetch(handler: (url: string) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => handler(String(input)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  nav.replace.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ProtectedRoute", () => {
  it("shows a skeleton while loading (never a private-UI flash)", async () => {
    let release!: (value: Response) => void;
    stubFetch((url) =>
      url.includes("/auth/me")
        ? new Promise<Response>((resolve) => {
            release = resolve;
          })
        : envelope("invalid_token", 400),
    );
    const { container } = render(
      <AuthProvider>
        <ProtectedRoute>
          <p>Private stuff</p>
        </ProtectedRoute>
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(container.querySelector('[aria-label="Loading your workspace"]')).not.toBeNull(),
    );
    expect(screen.queryByText("Private stuff")).toBeNull();
    release(userResponse(true));
    await waitFor(() => expect(screen.getByText("Private stuff")).not.toBeNull());
  });

  it("redirects logged-out visitors to /login", async () => {
    stubFetch((url) =>
      url.includes("/auth/me") ? envelope("unauthenticated", 401) : envelope("invalid_token", 400),
    );
    render(
      <AuthProvider>
        <ProtectedRoute>
          <p>Private stuff</p>
        </ProtectedRoute>
      </AuthProvider>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Private stuff")).toBeNull();
  });

  it("renders children for verified users", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return userResponse(true);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <ProtectedRoute>
          <p>Private stuff</p>
        </ProtectedRoute>
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("Private stuff")).not.toBeNull());
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("lets unverified users through without requireVerified", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return userResponse(false);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <ProtectedRoute>
          <p>Private stuff</p>
        </ProtectedRoute>
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText("Private stuff")).not.toBeNull());
  });
});
