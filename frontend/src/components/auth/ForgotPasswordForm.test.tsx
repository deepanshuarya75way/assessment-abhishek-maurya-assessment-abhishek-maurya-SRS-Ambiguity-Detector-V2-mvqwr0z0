// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ForgotPasswordForm } from "./ForgotPasswordForm";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ForgotPasswordForm", () => {
  it("blocks invalid email with no request", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<ForgotPasswordForm />);
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByText("Enter your email address.")).not.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers with identical non-committal copy (anti-enumeration)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({})),
    );
    render(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email"), "nobody-knows@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Check your inbox" })).not.toBeNull(),
    );
    expect(screen.getByRole("status").textContent?.replace(/\s+/g, " ")).toBe(
      "If an account exists for this email, a reset link is on its way — it expires in 60 minutes.",
    );
  });

  it("lets the user try a different email", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({})),
    );
    render(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Check your inbox" })).not.toBeNull(),
    );
    await user.click(screen.getByRole("button", { name: "Use a different email" }));
    expect(screen.getByRole("heading", { name: "Reset your password" })).not.toBeNull();
    expect(screen.getByRole("form", { name: "Request password reset" })).not.toBeNull();
  });

  it("maps rate_limited honestly", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("rate_limited", 429)),
    );
    render(<ForgotPasswordForm />);
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "Too many attempts. Please try again later.",
      ),
    );
  });
});
