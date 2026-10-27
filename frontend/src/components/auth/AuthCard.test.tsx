// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MotionConfig } from "motion/react";

import { AuthProvider } from "./AuthProvider";
import { AuthCard } from "./AuthCard";

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
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
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

const USER = {
  id: "user-1",
  email: "ada@example.com",
  display_name: "Ada",
  is_verified: false,
  is_active: true,
  created_at: "2026-09-24T00:00:00Z",
};

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function stubLoggedOut(
  handler?: (url: string, init?: RequestInit) => Response | Promise<Response> | null,
) {
  return stubFetch((url, init) => {
    const override = handler?.(url, init);
    if (override) return override;
    if (url.includes("/auth/me")) return envelope("unauthenticated", 401);
    return envelope("invalid_token", 400);
  });
}

// NOTE: label queries are scoped with `within()` to the visible form — jsdom
// loads no stylesheets, so `display: none` doesn't hide the inactive form from
// text queries (real browsers + role queries exclude it via aria-hidden).
function loginForm() {
  return within(screen.getByRole("form", { name: "Log in" }));
}

function signupForm() {
  return within(screen.getByRole("form", { name: "Create account" }));
}

beforeEach(() => {
  nav.replace.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe("AuthCard", () => {
  it("shows the login form by default and keeps signup hidden", async () => {
    stubLoggedOut();
    render(
      <AuthProvider>
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("form", { name: "Log in" })).not.toBeNull());
    expect(screen.queryByRole("form", { name: "Create account" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Welcome back" })).not.toBeNull();
    // The only visible "Create account" is the blade's switch (submit is hidden).
    expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull();
    // Mobile strip by default (no matchMedia in jsdom) — desktop panel absent.
    expect(document.body.textContent?.includes("SESSIONS IN HTTPONLY")).toBe(false);
  });

  it("shows signup for initialMode=signup", async () => {
    stubLoggedOut();
    render(
      <AuthProvider>
        <AuthCard initialMode="signup" />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("form", { name: "Create account" })).not.toBeNull(),
    );
    expect(screen.queryByRole("form", { name: "Log in" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Create your account" })).not.toBeNull();
  });

  it("sweeps to signup, announces it, and focuses the name field", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    const { container } = render(
      <AuthProvider>
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("form", { name: "Log in" })).not.toBeNull());

    await user.click(screen.getByRole("button", { name: "Create account" }));
    // Mid-sweep: card is busy, swap hasn't happened yet.
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByRole("form", { name: "Create account" })).toBeNull();

    // Swap lands mid-cover (~380ms); full settle follows (~700ms).
    await screen.findByRole("form", { name: "Create account" }, { timeout: 3000 });
    expect(screen.queryByRole("form", { name: "Log in" })).toBeNull();
    await waitFor(() => expect(container.querySelector('[aria-busy="true"]')).toBeNull(), {
      timeout: 3000,
    });
    expect(screen.getByText("Showing the create-account form.")).not.toBeNull();
    expect(document.activeElement).toBe(signupForm().getByLabelText("Name"));
    // Blade now invites the way back.
    expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull();
  });

  it("ignores re-entry mid-sweep (single transition, single landing)", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    const { container } = render(
      <AuthProvider>
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("form", { name: "Log in" })).not.toBeNull());
    const switchButton = screen.getByRole("button", { name: "Create account" });
    await user.click(switchButton);
    expect(switchButton.getAttribute("tabindex")).toBe("-1");
    await user.click(switchButton);
    await screen.findByRole("form", { name: "Create account" }, { timeout: 3000 });
    await waitFor(() => expect(container.querySelector('[aria-busy="true"]')).toBeNull(), {
      timeout: 3000,
    });
    expect(document.activeElement).toBe(signupForm().getByLabelText("Name"));
  });

  it("swaps instantly under reduced motion", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    render(
      <MotionConfig reducedMotion="always">
        <AuthProvider>
          <AuthCard initialMode="login" />
        </AuthProvider>
      </MotionConfig>,
    );
    await waitFor(() => expect(screen.getByRole("form", { name: "Log in" })).not.toBeNull());
    await user.click(screen.getByRole("button", { name: "Create account" }));
    // No sweep: the form is already there, synchronously.
    expect(screen.getByRole("form", { name: "Create account" })).not.toBeNull();
    expect(screen.getByText("Showing the create-account form.")).not.toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(signupForm().getByLabelText("Name")));
  });

  it("renders the desktop panel on wide viewports", async () => {
    stubLoggedOut();
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      media: "(min-width: 640px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }) as unknown as typeof window.matchMedia;
    render(
      <AuthProvider>
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("form", { name: "Log in" })).not.toBeNull());
    expect(document.body.textContent).toContain("SESSIONS IN HTTPONLY");
    expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull();
  });

  it("redirects authenticated visitors to the landing path (no form flash)", async () => {
    stubFetch((url) => {
      if (url.includes("/auth/me")) return jsonResponse(USER);
      return envelope("invalid_token", 400);
    });
    render(
      <AuthProvider>
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("shows a loading skeleton while identity resolves", async () => {
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
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(container.querySelector('[aria-label="Loading account access"]')).not.toBeNull(),
    );
    expect(screen.queryByRole("form")).toBeNull();
    release(envelope("unauthenticated", 401));
    await screen.findByRole("form", { name: "Log in" }, { timeout: 3000 });
  });

  it("navigates to the landing path after login", async () => {
    const user = userEvent.setup();
    stubLoggedOut((url) => {
      if (url.includes("/auth/login")) {
        return jsonResponse({ id: "user-1", email: USER.email, is_verified: true });
      }
      return null;
    });
    render(
      <AuthProvider>
        <AuthCard initialMode="login" />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("form", { name: "Log in" })).not.toBeNull());
    const form = loginForm();
    await user.type(form.getByLabelText("Email"), "ada@example.com");
    await user.type(form.getByLabelText("Password"), "correct-password-1");
    await user.click(form.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("starts the session and navigates after signup", async () => {
    const user = userEvent.setup();
    let registered = false;
    stubLoggedOut((url) => {
      if (url.includes("/auth/register")) {
        registered = true;
        return jsonResponse({ id: "user-1", email: USER.email, is_verified: true }, 201);
      }
      if (url.includes("/auth/me") && registered) return jsonResponse(USER);
      return null;
    });
    render(<AuthProvider><AuthCard initialMode="signup" /></AuthProvider>);
    await waitFor(() => expect(screen.getByRole("form", { name: "Create account" })).not.toBeNull());
    const form = signupForm();
    await user.type(form.getByLabelText("Name"), "Ada");
    await user.type(form.getByLabelText("Email"), "ada@example.com");
    await user.type(form.getByLabelText("Password"), "correct-horse-battery9");
    await user.type(form.getByLabelText("Confirm password"), "correct-horse-battery9");
    await user.click(form.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/dashboard"));
  });
});
