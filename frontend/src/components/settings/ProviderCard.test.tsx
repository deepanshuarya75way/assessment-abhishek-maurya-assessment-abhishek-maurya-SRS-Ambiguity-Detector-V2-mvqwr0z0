// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ProviderCredential, ProviderTestResult } from "@/types/providers";

import { ProviderCard } from "./ProviderCard";

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

function credential(overrides: Partial<ProviderCredential> = {}): ProviderCredential {
  return {
    id: "cred-groq",
    provider: "groq",
    label: "Work",
    masked_key: "••••••••••••1234",
    is_enabled: true,
    is_default: false,
    fallback_rank: 0,
    key_version: 1,
    last_tested_at: null,
    last_test_status: null,
    ...overrides,
  };
}

interface CardCallbacks {
  onChanged: (row: ProviderCredential) => void;
  onDefaultClaimed: () => void;
  onTested: () => void;
  onReplaceKey: (credential: ProviderCredential) => void;
  onRemove: (credential: ProviderCredential) => void;
}

function callbacks(): CardCallbacks & {
  fns: Record<keyof CardCallbacks, ReturnType<typeof vi.fn>>;
} {
  const fns = {
    onChanged: vi.fn(),
    onDefaultClaimed: vi.fn(),
    onTested: vi.fn(),
    onReplaceKey: vi.fn(),
    onRemove: vi.fn(),
  };
  return { ...fns, fns };
}

function renderCard(row: ProviderCredential, cbs: CardCallbacks) {
  render(
    <ProviderCard
      credential={row}
      onChanged={cbs.onChanged}
      onDefaultClaimed={cbs.onDefaultClaimed}
      onTested={cbs.onTested}
      onReplaceKey={cbs.onReplaceKey}
      onRemove={cbs.onRemove}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ProviderCard rendering", () => {
  it("renders identity, masked key, and never-tested freshness", () => {
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({})),
    );
    renderCard(credential(), cbs);

    expect(screen.getByRole("heading", { name: "Groq" })).toBeDefined();
    expect(screen.getByText("Work")).toBeDefined();
    expect(screen.getByText("••••••••••••1234")).toBeDefined();
    expect(screen.getByText("Never tested")).toBeDefined();
    // The masked value is inert text — not inside any editable field.
    for (const input of document.querySelectorAll("input")) {
      expect(input.value).not.toContain("••••");
    }
  });

  it("renders status chips for enabled, default, and last-test verdicts", () => {
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({})),
    );
    const { unmount } = render(
      <ProviderCard
        credential={credential({
          is_default: true,
          last_tested_at: "2026-09-24T10:00:00Z",
          last_test_status: "ok",
        })}
        onChanged={cbs.onChanged}
        onDefaultClaimed={cbs.onDefaultClaimed}
        onTested={cbs.onTested}
        onReplaceKey={cbs.onReplaceKey}
        onRemove={cbs.onRemove}
      />,
    );
    const chips = within(screen.getByRole("list", { name: "Groq status" }));
    expect(chips.getByText("Default")).toBeDefined();
    expect(chips.getByText("Enabled")).toBeDefined();
    expect(screen.getByText(/Passed ·/)).toBeDefined();
    unmount();

    renderCard(
      credential({
        is_enabled: false,
        last_test_status: "failed",
        last_tested_at: "2026-09-24T10:00:00Z",
      }),
      cbs,
    );
    const chipsAfter = within(screen.getByRole("list", { name: "Groq status" }));
    expect(chipsAfter.getByText("Disabled")).toBeDefined();
    expect(chipsAfter.queryByText("Default")).toBeNull();
    expect(screen.getByText(/Failed ·/)).toBeDefined();
  });

  it("shows Set as default only for enabled non-default rows", () => {
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({})),
    );
    renderCard(credential(), cbs);
    expect(screen.getByRole("button", { name: "Set as default" })).toBeDefined();
    cleanup();

    renderCard(credential({ is_default: true }), callbacks());
    expect(screen.queryByRole("button", { name: "Set as default" })).toBeNull();
    cleanup();

    renderCard(credential({ is_enabled: false }), callbacks());
    expect(screen.queryByRole("button", { name: "Set as default" })).toBeNull();
  });

  it("exposes an accessible enable switch reflecting server state", () => {
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({})),
    );
    renderCard(credential(), cbs);
    const disable = screen.getByRole("switch", { name: "Disable Groq" });
    expect(disable.getAttribute("aria-checked")).toBe("true");
    cleanup();

    renderCard(credential({ is_enabled: false }), callbacks());
    expect(screen.getByRole("switch", { name: "Enable Groq" }).getAttribute("aria-checked")).toBe(
      "false",
    );
  });
});

describe("ProviderCard test flow", () => {
  it("shows pending state, prevents duplicates, then renders the verdict", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    let release!: (response: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const fetchMock = vi.fn(async () => gate);
    vi.stubGlobal("fetch", fetchMock);
    renderCard(credential(), cbs);

    const testButton = screen.getByRole("button", { name: "Test connection" });
    await user.click(testButton);
    await user.click(testButton); // duplicate while pending
    expect(screen.getByRole("button", { name: "Testing…" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Testing…" })).toHaveProperty("disabled", true);
    release(jsonResponse({ ok: true, models: ["a", "b"], latency_ms: 42, error: null }));
    expect(
      await screen.findByText(/Connection works — 2 models available \(42 ms\)/),
    ).toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(cbs.fns.onTested).toHaveBeenCalledTimes(1);
  });

  it("renders failed verdicts with the backend's user-safe text", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    const verdict: ProviderTestResult = {
      ok: false,
      models: [],
      latency_ms: 9,
      error: "Key rejected by provider.",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(verdict)),
    );
    renderCard(credential(), cbs);

    await user.click(screen.getByRole("button", { name: "Test connection" }));
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("Connection test failed.");
    expect(status.textContent).toContain("Key rejected by provider.");
    expect(cbs.fns.onTested).toHaveBeenCalledTimes(1);
  });

  it("renders the pre-adapter unavailable verdict as data, not an error", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          ok: false,
          models: [],
          latency_ms: 0,
          error: "Provider integration is not available yet.",
        }),
      ),
    );
    renderCard(credential(), cbs);

    await user.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("Provider integration is not available yet.")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("maps test failures to code copy (rate limit, session)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse("rate_limited", 429)),
    );
    renderCard(credential(), callbacks());
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText(/Too many connection tests/)).toBeDefined();
    cleanup();

    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
        return errorResponse("unauthenticated", 401);
      }),
    );
    renderCard(credential(), cbs);
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Your session has expired.");
    expect(screen.getByRole("link", { name: "Sign in again" })).toBeDefined();
    expect(cbs.fns.onTested).not.toHaveBeenCalled();
  });
});

describe("ProviderCard enable/disable and default", () => {
  it("disables with pending state and reports the server row", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    const disabled = credential({ is_enabled: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(disabled)),
    );
    renderCard(credential(), cbs);

    await user.click(screen.getByRole("switch", { name: "Disable Groq" }));
    await waitFor(() => expect(cbs.fns.onChanged).toHaveBeenCalledWith(disabled));
  });

  it("keeps server state on toggle failure (no optimistic flip)", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse("conflict", 409)),
    );
    renderCard(credential({ is_enabled: false }), cbs);

    await user.click(screen.getByRole("switch", { name: "Enable Groq" }));
    expect(await screen.findByText(/conflicts with another credential/)).toBeDefined();
    expect(screen.getByRole("switch", { name: "Enable Groq" }).getAttribute("aria-checked")).toBe(
      "false",
    );
    expect(cbs.fns.onChanged).not.toHaveBeenCalled();
  });

  it("claims default and notifies the parent to refetch", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(credential({ is_default: true }))),
    );
    renderCard(credential(), cbs);

    await user.click(screen.getByRole("button", { name: "Set as default" }));
    await waitFor(() => expect(cbs.fns.onDefaultClaimed).toHaveBeenCalledTimes(1));
  });

  it("surfaces default-claim rejections inline", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse("conflict", 409)),
    );
    renderCard(credential(), cbs);

    await user.click(screen.getByRole("button", { name: "Set as default" }));
    expect(await screen.findByText(/conflicts with another credential/)).toBeDefined();
    expect(cbs.fns.onDefaultClaimed).not.toHaveBeenCalled();
  });
});

describe("ProviderCard actions", () => {
  it("delegates replace-key and remove to the parent (no direct mutation)", async () => {
    const user = userEvent.setup();
    const cbs = callbacks();
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    const row = credential();
    renderCard(row, cbs);

    await user.click(screen.getByRole("button", { name: "Replace key" }));
    expect(cbs.fns.onReplaceKey).toHaveBeenCalledWith(row);
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(cbs.fns.onRemove).toHaveBeenCalledWith(row);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
