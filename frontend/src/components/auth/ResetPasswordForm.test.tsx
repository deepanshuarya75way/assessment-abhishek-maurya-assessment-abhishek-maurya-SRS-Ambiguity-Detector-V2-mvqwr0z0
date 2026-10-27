// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ResetPasswordForm } from "./ResetPasswordForm";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: nav.replace,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const TOKEN = "r".repeat(43);

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `server ${code}` } }, status);
}

beforeEach(() => {
  nav.search = "";
  nav.replace.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ResetPasswordForm", () => {
  it("shows the invalid-link panel without a token", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<ResetPasswordForm />);
    expect(screen.getByRole("heading", { name: "Invalid reset link" })).not.toBeNull();
    expect(screen.getByRole("link", { name: "Request a new link" }).getAttribute("href")).toBe(
      "/forgot-password",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects mismatched passwords client-side", async () => {
    nav.search = `token=${TOKEN}`;
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<ResetPasswordForm />);
    await user.type(screen.getByLabelText("New password"), "new-password-12x");
    await user.type(screen.getByLabelText("Confirm new password"), "new-password-12y");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(screen.getByText("Passwords don't match.")).not.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("resets with the link token and guides to login (never auto-login)", async () => {
    nav.search = `token=${TOKEN}`;
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.body) bodies.push(JSON.parse(init.body as string));
        return jsonResponse({});
      }),
    );
    render(<ResetPasswordForm />);
    await user.type(screen.getByLabelText("New password"), "brand-new-password-1");
    await user.type(screen.getByLabelText("Confirm new password"), "brand-new-password-1");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Password updated" })).not.toBeNull(),
    );
    expect(bodies).toEqual([{ token: TOKEN, new_password: "brand-new-password-1" }]);
    expect(document.body.textContent?.includes(TOKEN)).toBe(false);
    expect(nav.replace).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Back to log in" }));
    expect(nav.replace).toHaveBeenCalledWith("/login");
  });

  it("maps an expired link honestly", async () => {
    nav.search = `token=${TOKEN}`;
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("invalid_token", 400)),
    );
    render(<ResetPasswordForm />);
    await user.type(screen.getByLabelText("New password"), "brand-new-password-1");
    await user.type(screen.getByLabelText("Confirm new password"), "brand-new-password-1");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "This reset link is invalid or has expired.",
      ),
    );
  });
});
