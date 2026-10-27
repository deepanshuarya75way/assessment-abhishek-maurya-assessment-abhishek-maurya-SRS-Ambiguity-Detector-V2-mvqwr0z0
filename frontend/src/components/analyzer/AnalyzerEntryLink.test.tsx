// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { AuthProvider } from "@/components/auth/AuthProvider";

import { AnalyzerEntryLink } from "./AnalyzerEntryLink";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function userResponse() {
  return jsonResponse({
    id: "user-1",
    email: "ada@example.com",
    display_name: "Ada",
    is_verified: true,
    is_active: true,
    created_at: "2026-09-24T00:00:00Z",
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AnalyzerEntryLink", () => {
  it("shows the analyzer link to signed-in users", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => userResponse()),
    );
    render(
      <AuthProvider>
        <AnalyzerEntryLink />
      </AuthProvider>,
    );
    const link = await screen.findByRole("link", { name: "Open analyzer" });
    expect(link.getAttribute("href")).toBe("/analyzer");
  });

  it("renders nothing while signed out", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ error: { code: "unauthenticated", message: "no" } }, 401),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(
      <AuthProvider>
        <AnalyzerEntryLink />
      </AuthProvider>,
    );
    // Await the /me resolution (plus its failed silent refresh); the link
    // renders null in every non-authenticated state, so emptiness is stable.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
