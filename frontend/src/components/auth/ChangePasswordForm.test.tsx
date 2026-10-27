// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChangePasswordForm } from "./ChangePasswordForm";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: `server ${code}` } }, status);
}

function stubFetch(handler: (url: string) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => handler(String(input)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Current password"), "old-password-12x");
  await user.type(screen.getByLabelText("New password"), "brand-new-password-1");
  await user.type(screen.getByLabelText("Confirm new password"), "brand-new-password-1");
}

describe("ChangePasswordForm", () => {
  it("blocks empty submit with field errors and no request", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch(() => jsonResponse({}));
    render(<ChangePasswordForm />);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(screen.getByText("Enter your current password.")).not.toBeNull();
    expect(screen.getByText("Enter a password.")).not.toBeNull();
    expect(screen.getByText("Confirm your password.")).not.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("updates, confirms, and clears the fields", async () => {
    const user = userEvent.setup();
    stubFetch(() => jsonResponse({}));
    render(<ChangePasswordForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Password updated."));
    expect((screen.getByLabelText("Current password") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("New password") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Confirm new password") as HTMLInputElement).value).toBe("");
  });

  it("lands current_password_incorrect on the current-password field", async () => {
    const user = userEvent.setup();
    stubFetch(() => envelope("current_password_incorrect", 401));
    render(<ChangePasswordForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    await waitFor(() => expect(screen.getByText("Current password is incorrect.")).not.toBeNull());
    const current = screen.getByLabelText("Current password") as HTMLInputElement;
    expect(current.getAttribute("aria-invalid")).toBe("true");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("surfaces a logged-out session through the silent-refresh path", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch((url) =>
      url.includes("/auth/refresh")
        ? envelope("invalid_token", 400)
        : envelope("unauthenticated", 401),
    );
    render(<ChangePasswordForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Update password" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "Your session has expired. Please log in again.",
      ),
    );
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/auth/refresh")),
    ).toHaveLength(1);
  });
});
