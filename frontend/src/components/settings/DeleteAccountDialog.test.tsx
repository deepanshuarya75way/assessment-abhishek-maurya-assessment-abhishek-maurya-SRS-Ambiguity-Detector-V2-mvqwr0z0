// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DeleteAccountDialog } from "./DeleteAccountDialog";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "Server copy (never displayed)." } }, status);
}

function stubFetch(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init)),
  );
}

function renderDialog(overrides: { onClose?: () => void; onDeleted?: () => void } = {}) {
  const onClose = overrides.onClose ?? vi.fn();
  const onDeleted = overrides.onDeleted ?? vi.fn();
  render(<DeleteAccountDialog email="ada@example.com" onClose={onClose} onDeleted={onDeleted} />);
  return { onClose, onDeleted };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("DeleteAccountDialog", () => {
  it("confirms only on the exact word DELETE, then reports the 204", async () => {
    const user = userEvent.setup();
    const seen: Array<{ url: string; body: unknown }> = [];
    stubFetch((url, init) => {
      if (url.endsWith("/auth/account")) {
        seen.push({ url, body: JSON.parse(String(init?.body)) });
        return new Response(null, { status: 204 });
      }
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      return errorResponse("bad_response", 500);
    });
    const { onClose, onDeleted } = renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    const confirm = within(dialog).getByRole("button", { name: "Delete account" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "delete");
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.clear(within(dialog).getByLabelText("Type DELETE to confirm"));
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE ");
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.clear(within(dialog).getByLabelText("Type DELETE to confirm"));
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(confirm);
    expect(onDeleted).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(seen).toEqual([
      { url: expect.stringContaining("/auth/account"), body: { confirmation: "DELETE" } },
    ]);
  });

  it("focuses the safe default and cancels on Escape or the close button", async () => {
    const user = userEvent.setup();
    stubFetch(() => errorResponse("bad_response", 500));
    const { onClose, onDeleted } = renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    expect(document.activeElement).toBe(
      within(dialog).getByRole("button", { name: "Keep my account" }),
    );
    expect(within(dialog).getByRole("button", { name: "Close dialog" })).toBeDefined();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onDeleted).not.toHaveBeenCalled();

    cleanup();
    const rerendered = renderDialog();
    await user.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(rerendered.onClose).toHaveBeenCalledTimes(1);
    expect(rerendered.onDeleted).not.toHaveBeenCalled();
  });

  it("a refused delete stays open with mapped copy", async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (url.endsWith("/auth/account")) return errorResponse("rate_limited", 429);
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      return errorResponse("bad_response", 500);
    });
    const { onClose, onDeleted } = renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(within(dialog).getByRole("button", { name: "Delete account" }));
    expect(
      await within(dialog).findByText("Too many attempts. Please try again later."),
    ).toBeDefined();
    expect(onDeleted).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("a dead session reports honestly instead of guessing the outcome", async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (url.endsWith("/auth/account")) return errorResponse("unauthenticated", 401);
      if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
      return errorResponse("bad_response", 500);
    });
    const { onDeleted } = renderDialog();
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(within(dialog).getByRole("button", { name: "Delete account" }));
    expect(await within(dialog).findByText(/session ended before this finished/)).toBeDefined();
    expect(within(dialog).getByRole("link", { name: "sign in" })).toBeDefined();
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
