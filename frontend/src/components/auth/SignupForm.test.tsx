// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthProvider } from "./AuthProvider";
import { SignupForm } from "./SignupForm";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `server ${code}` } }, status);
}

function stubLoggedOut(
  handler?: (url: string, init?: RequestInit) => Response | Promise<Response> | null,
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const override = handler?.(url, init);
    if (override) return override;
    if (url.includes("/auth/me")) return envelope("unauthenticated", 401);
    return envelope("invalid_token", 400);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function fillValid(user: ReturnType<typeof userEvent.setup>, overrides?: { email?: string }) {
  await user.type(screen.getByLabelText("Name"), "  Ada   Lovelace ");
  await user.type(screen.getByLabelText("Email"), overrides?.email ?? "ADA@Example.COM");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery9");
  await user.type(screen.getByLabelText("Confirm password"), "correct-horse-battery9");
}

describe("SignupForm", () => {
  it("blocks empty submit with field errors and no request", async () => {
    const user = userEvent.setup();
    const fetchMock = stubLoggedOut();
    render(
      <AuthProvider>
        <SignupForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull(),
    );
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Enter your name.")).not.toBeNull();
    expect(screen.getByText("Enter your email address.")).not.toBeNull();
    expect(screen.getByText("Enter a password.")).not.toBeNull();
    expect(screen.getByText("Confirm your password.")).not.toBeNull();
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/auth/register")),
    ).toHaveLength(0);
  });

  it("rejects short, mismatched, and email-derived passwords", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    render(
      <AuthProvider>
        <SignupForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull(),
    );
    await user.type(screen.getByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Email"), "ada.lovelace@example.com");
    await user.type(screen.getByLabelText("Password"), "short-11!");
    await user.type(screen.getByLabelText("Confirm password"), "something-else-12");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Use at least 12 characters.")).not.toBeNull();
    expect(screen.getByText("Passwords don't match.")).not.toBeNull();
  });

  it("rejects passwords containing the email local part", async () => {
    const user = userEvent.setup();
    stubLoggedOut();
    render(
      <AuthProvider>
        <SignupForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull(),
    );
    await user.type(screen.getByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Email"), "lovelace@example.com");
    await user.type(screen.getByLabelText("Password"), "xxLovelace12xx");
    await user.type(screen.getByLabelText("Confirm password"), "xxLovelace12xx");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Don't include your email address in your password.")).not.toBeNull();
  });

  it("registers with collapsed name + normalized email and reports the email", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    stubLoggedOut((url, init) => {
      if (init?.body) bodies.push(JSON.parse(init.body as string));
      if (url.includes("/auth/register")) {
        return jsonResponse({ id: "user-1", email: "ada@example.com", is_verified: false }, 201);
      }
      return null;
    });
    const onSuccess = vi.fn();
    render(
      <AuthProvider>
        <SignupForm onSuccess={onSuccess} />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull(),
    );
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("ada@example.com"));
    expect(bodies).toContainEqual({
      name: "Ada Lovelace",
      email: "ada@example.com",
      password: "correct-horse-battery9",
    });
  });

  it("maps password_too_weak to guidance (common-password denylist is server-side)", async () => {
    const user = userEvent.setup();
    stubLoggedOut((url) =>
      url.includes("/auth/register") ? envelope("password_too_weak", 400) : null,
    );
    render(
      <AuthProvider>
        <SignupForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull(),
    );
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "This password doesn't meet our requirements — try something longer and less predictable.",
      ),
    );
  });

  it("maps server validation details onto fields", async () => {
    const user = userEvent.setup();
    stubLoggedOut((url) =>
      url.includes("/auth/register")
        ? jsonResponse(
            {
              error: {
                code: "validation_error",
                message: "Request validation failed.",
                details: [{ loc: ["body", "email"], msg: "value is not a valid email address" }],
              },
            },
            400,
          )
        : null,
    );
    render(
      <AuthProvider>
        <SignupForm onSuccess={vi.fn()} />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create account" })).not.toBeNull(),
    );
    await fillValid(user, { email: "x@y.zz" });
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "Please check the highlighted fields and try again.",
      ),
    );
    // The email field carries the mapped error (id-linked, aria-invalid).
    const email = screen.getByLabelText("Email") as HTMLInputElement;
    expect(email.getAttribute("aria-invalid")).toBe("true");
    expect(email.getAttribute("aria-describedby")).not.toBeNull();
  });
});
