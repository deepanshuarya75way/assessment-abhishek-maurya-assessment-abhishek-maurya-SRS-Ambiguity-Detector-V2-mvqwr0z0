// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthProvider } from "./AuthProvider";
import { LoginForm } from "./LoginForm";

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

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Logged-out init: /me 401, refresh 400. */
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

const USER = {
  id: "user-1",
  email: "ada@example.com",
  display_name: "Ada",
  is_verified: true,
  is_active: true,
  created_at: "2026-09-24T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("LoginForm", () => {
  it("blocks empty submit with field errors and no request", async () => {
    const user = userEvent.setup();
    const fetchMock = stubLoggedOut();
    const onSuccess = vi.fn();
    render(
      <AuthProvider>
        <LoginForm onSuccess={onSuccess} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByText("Enter your email address.")).not.toBeNull();
    expect(screen.getByText("Enter your password.")).not.toBeNull();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/auth/login")),
    ).toHaveLength(0);
  });

  it("validates the email shape client-side", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    render(
      <AuthProvider>
        <LoginForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByText("Enter a valid email address.")).not.toBeNull();
  });

  it("maps invalid_credentials to the form alert (never the server string)", async () => {
    const user = userEvent.setup();
    stubLoggedOut((url) =>
      url.includes("/auth/login") ? envelope("invalid_credentials", 401) : null,
    );
    render(
      <AuthProvider>
        <LoginForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password-1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("Invalid email or password."),
    );
    expect(document.body.textContent?.includes("SERVER SAYS")).toBe(false);
  });

  it("succeeds with a normalized email and calls onSuccess", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    stubLoggedOut((url, init) => {
      if (init?.body) bodies.push(JSON.parse(init.body as string));
      if (url.includes("/auth/login")) {
        return jsonResponse({ id: "user-1", email: USER.email, is_verified: true });
      }
      return null;
    });
    const onSuccess = vi.fn();
    render(
      <AuthProvider>
        <LoginForm onSuccess={onSuccess} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    await user.type(screen.getByLabelText("Email"), "  ADA@Example.COM ");
    await user.type(screen.getByLabelText("Password"), "correct-password-1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(bodies).toContainEqual({ email: "ada@example.com", password: "correct-password-1" });
  });

  it("issues a single login POST under double submit", async () => {
    const user = userEvent.setup();
    let loginCalls = 0;
    let release!: (value: Response) => void;
    stubLoggedOut((url) => {
      if (url.includes("/auth/login")) {
        loginCalls += 1;
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }
      return null;
    });
    render(
      <AuthProvider>
        <LoginForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-password-1");
    const submit = screen.getByRole("button", { name: /logging in|log in/i });
    await user.click(submit);
    expect(
      screen.getByRole("button", { name: "Logging in…" }).getAttribute("disabled"),
    ).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Logging in…" }));
    expect(loginCalls).toBe(1);
    release(jsonResponse({ id: "user-1", email: USER.email, is_verified: true }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Log in" }).getAttribute("disabled")).toBeNull(),
    );
  });

  it("toggles password visibility accessibly", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    render(
      <AuthProvider>
        <LoginForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    const password = screen.getByLabelText("Password") as HTMLInputElement;
    expect(password.type).toBe("password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password.type).toBe("text");
    expect(screen.getByRole("button", { name: "Hide password" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password.type).toBe("password");
  });

  it("links to forgot-password", async () => {
    stubLoggedOut();
    render(
      <AuthProvider>
        <LoginForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Log in" })).not.toBeNull());
    expect(screen.getByText("Forgot password?").getAttribute("href")).toBe("/forgot-password");
  });
});
