// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthProvider } from "@/components/auth/AuthProvider";

import { ProfileSection } from "./ProfileSection";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
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

function errorResponse(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "Server copy (never displayed)." } }, status);
}

function profileResponse(displayName: string | null = "Ada"): Response {
  return jsonResponse({
    email: "ada@example.com",
    display_name: displayName,
    is_verified: true,
    is_active: true,
    created_at: "2026-09-24T00:00:00Z",
  });
}

function userResponse(): Response {
  return jsonResponse({
    id: "user-1",
    email: "ada@example.com",
    display_name: "Ada",
    is_verified: true,
    is_active: true,
    created_at: "2026-09-24T00:00:00Z",
  });
}

function stubFetch(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init)),
  );
}

function renderSection() {
  render(
    <AuthProvider>
      <ProfileSection />
    </AuthProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("ProfileSection", () => {
  it("shows a skeleton while loading, then the email and name", async () => {
    let release!: (response: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    stubFetch((url) => {
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      if (url.endsWith("/settings/profile")) return gate as unknown as Response;
      return errorResponse("bad_response", 500);
    });
    renderSection();
    expect(await screen.findByLabelText("Loading profile")).toBeDefined();
    release(profileResponse());
    expect((await screen.findByLabelText("Display name")) as HTMLInputElement).toBeDefined();
    expect(screen.getByText("ada@example.com")).toBeDefined();
  });

  it("session-gone load nudges to sign in without a retry loop", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return errorResponse("unauthenticated", 401);
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      if (url.endsWith("/settings/profile")) return errorResponse("unauthenticated", 401);
      return errorResponse("bad_response", 500);
    });
    renderSection();
    expect(await screen.findByText(/session expired/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Sign in again" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("load failure offers a retry that recovers", async () => {
    const user = userEvent.setup();
    let calls = 0;
    stubFetch((url) => {
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      if (url.endsWith("/settings/profile")) {
        calls += 1;
        return calls === 1 ? errorResponse("internal_error", 500) : profileResponse();
      }
      return errorResponse("bad_response", 500);
    });
    renderSection();
    expect(await screen.findByText("Something went wrong. Please try again.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Display name")).toBeDefined();
  });

  it("rejects a wrong-shaped profile honestly", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      if (url.endsWith("/settings/profile")) return jsonResponse({ email: 42 });
      return errorResponse("bad_response", 500);
    });
    renderSection();
    expect(await screen.findByText("The service returned an unexpected response.")).toBeDefined();
  });

  it("maps a rejected save onto the field with server-proof copy", async () => {
    const user = userEvent.setup();
    stubFetch((url, init) => {
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      if (url.endsWith("/settings/profile") && init?.method === "PATCH") {
        return errorResponse("validation_error", 400);
      }
      if (url.endsWith("/settings/profile")) return profileResponse();
      return errorResponse("bad_response", 500);
    });
    renderSection();
    await user.type(await screen.findByLabelText("Display name"), "!");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(
      await screen.findByText("That name can't be saved — keep it under 100 characters."),
    ).toBeDefined();
    expect(screen.queryByText("Profile saved.")).toBeNull();
  });

  it("a dead session at save time resolves to the sign-in nudge", async () => {
    const user = userEvent.setup();
    stubFetch((url, init) => {
      if (url.includes("/auth/me")) return userResponse();
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      if (url.endsWith("/settings/profile") && init?.method === "PATCH") {
        return errorResponse("unauthenticated", 401);
      }
      if (url.endsWith("/settings/profile")) return profileResponse();
      return errorResponse("bad_response", 500);
    });
    renderSection();
    await screen.findByLabelText("Display name");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText(/session expired/)).toBeDefined();
  });
});
