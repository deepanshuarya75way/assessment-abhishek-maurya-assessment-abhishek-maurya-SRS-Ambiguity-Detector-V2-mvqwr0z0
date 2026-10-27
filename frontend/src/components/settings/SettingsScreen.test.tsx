// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthProvider } from "@/components/auth/AuthProvider";
import type { ProviderCredential, ProviderTestResult } from "@/types/providers";

import { SettingsScreen } from "./SettingsScreen";

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

const BULLETS = "••••••••••••";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(code: string, status: number): Response {
  return jsonResponse({ error: { code, message: "Server copy (never displayed)." } }, status);
}

function userResponse(verified = true): Response {
  return jsonResponse({
    id: "user-1",
    email: "ada@example.com",
    display_name: "Ada",
    is_verified: verified,
    is_active: true,
    created_at: "2026-09-24T00:00:00Z",
  });
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

function credential(overrides: Partial<ProviderCredential> = {}): ProviderCredential {
  return {
    id: "cred-groq",
    provider: "groq",
    label: "Work",
    masked_key: `${BULLETS}1234`,
    is_enabled: true,
    is_default: false,
    fallback_rank: 0,
    key_version: 1,
    last_tested_at: null,
    last_test_status: null,
    ...overrides,
  };
}

interface CapturedRequest {
  url: string;
  method: string;
  body: unknown;
}

type RouteHandler = (id: string, body: Record<string, unknown>) => Response | Promise<Response>;

/**
 * Fake `/ai/providers` backend mirroring server rules (enabled conflicts,
 * fingerprint conflicts, same-transaction default moves, verdict clearing
 * on rotate). Per-route overrides replace the default for error-path tests.
 */
function createStore(initial: ProviderCredential[]) {
  let rows = initial.map((row) => ({ ...row }));
  let counter = rows.length;
  const requests: CapturedRequest[] = [];
  const overrides: {
    list?: () => Response | Promise<Response>;
    create?: RouteHandler;
    patch?: RouteHandler;
    rotate?: RouteHandler;
    test?: RouteHandler;
    remove?: RouteHandler;
    getProfile?: () => Response | Promise<Response>;
    patchProfile?: RouteHandler;
    getPrivacy?: () => Response | Promise<Response>;
    patchPrivacy?: RouteHandler;
    exportPrivacy?: RouteHandler;
    purgeHistory?: RouteHandler;
    deleteAccount?: RouteHandler;
  } = {};
  let profileName: string | null = "Ada";
  let historyRetentionDays: number | null = null;
  let testVerdict: ProviderTestResult = { ok: true, models: ["m"], latency_ms: 7, error: null };

  function handler(input: RequestInfo | URL, init?: RequestInit): Response | Promise<Response> {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body =
      init?.body !== undefined ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    requests.push({ url, method, body });
    if (url.includes("/auth/me")) return userResponse(store.verified);
    if (url.includes("/auth/refresh")) return errorResponse("unauthenticated", 401);
    if (url.endsWith("/settings/profile") && method === "GET") {
      if (overrides.getProfile !== undefined) return overrides.getProfile();
      return profileResponse(profileName);
    }
    if (url.endsWith("/settings/profile") && method === "PATCH") {
      if (overrides.patchProfile !== undefined) return overrides.patchProfile("", body);
      const next = body.display_name;
      profileName = typeof next === "string" && next.trim() !== "" ? next.trim() : null;
      return profileResponse(profileName);
    }
    if (url.endsWith("/settings/privacy") && method === "GET") {
      if (overrides.getPrivacy !== undefined) return overrides.getPrivacy();
      return jsonResponse({ history_retention_days: historyRetentionDays });
    }
    if (url.endsWith("/settings/privacy") && method === "PATCH") {
      if (overrides.patchPrivacy !== undefined) return overrides.patchPrivacy("", body);
      historyRetentionDays =
        typeof body.history_retention_days === "number" ? body.history_retention_days : null;
      return jsonResponse({ history_retention_days: historyRetentionDays });
    }
    if (url.endsWith("/privacy/export") && method === "POST") {
      if (overrides.exportPrivacy !== undefined) return overrides.exportPrivacy("", body);
      return jsonResponse(
        {
          export_id: "export-token",
          download_url: "/api/v1/privacy/export/export-token",
          expires_at: "2026-09-24T00:15:00Z",
        },
        202,
      );
    }
    if (url.endsWith("/privacy/purge-history") && method === "POST") {
      if (overrides.purgeHistory !== undefined) return overrides.purgeHistory("", body);
      return jsonResponse({ deleted_analyses: 2, deleted_documents: 1 });
    }
    if (url.endsWith("/auth/account") && method === "DELETE") {
      if (overrides.deleteAccount !== undefined) return overrides.deleteAccount("", body);
      if (body.confirmation !== "DELETE") return errorResponse("validation_error", 400);
      return new Response(null, { status: 204 });
    }

    const testMatch = /\/ai\/providers\/([^/]+)\/test$/.exec(url);
    if (method === "POST" && testMatch?.[1] !== undefined) {
      const id = testMatch[1];
      if (overrides.test !== undefined) return overrides.test(id, body);
      const row = rows.find((candidate) => candidate.id === id);
      if (row === undefined) return errorResponse("ai_provider_not_found", 404);
      row.last_tested_at = "2026-09-24T12:00:00Z";
      row.last_test_status = testVerdict.ok ? "ok" : "failed";
      return jsonResponse(testVerdict);
    }
    const rotateMatch = /\/ai\/providers\/([^/]+)\/rotate-key$/.exec(url);
    if (method === "POST" && rotateMatch?.[1] !== undefined) {
      const id = rotateMatch[1];
      if (overrides.rotate !== undefined) return overrides.rotate(id, body);
      const row = rows.find((candidate) => candidate.id === id);
      if (row === undefined) return errorResponse("ai_provider_not_found", 404);
      const key = typeof body.api_key === "string" ? body.api_key : "";
      row.masked_key = `${BULLETS}${key.slice(-4)}`;
      row.last_tested_at = null;
      row.last_test_status = null;
      return jsonResponse({ ...row });
    }
    const idMatch = /\/ai\/providers\/([^/]+)$/.exec(url);
    if (idMatch?.[1] !== undefined) {
      const id = idMatch[1];
      if (method === "PATCH") {
        if (overrides.patch !== undefined) return overrides.patch(id, body);
        const row = rows.find((candidate) => candidate.id === id);
        if (row === undefined) return errorResponse("ai_provider_not_found", 404);
        if (typeof body.label !== "undefined") row.label = body.label as string | null;
        if (body.is_enabled === false) {
          row.is_enabled = false;
          row.is_default = false;
        }
        if (body.is_enabled === true) row.is_enabled = true;
        if (body.is_default === true) {
          for (const other of rows) other.is_default = false;
          row.is_default = true;
        }
        if (body.is_default === false) row.is_default = false;
        return jsonResponse({ ...row });
      }
      if (method === "DELETE") {
        if (overrides.remove !== undefined) return overrides.remove(id, body);
        rows = rows.filter((candidate) => candidate.id !== id);
        return new Response(null, { status: 204 });
      }
    }
    if (url.endsWith("/ai/providers") && method === "POST") {
      if (overrides.create !== undefined) return overrides.create("", body);
      const provider = body.provider as string;
      if (rows.some((row) => row.provider === provider && row.is_enabled)) {
        return errorResponse("conflict", 409);
      }
      counter += 1;
      const key = typeof body.api_key === "string" ? body.api_key : "";
      const row = credential({
        id: `cred-${counter}`,
        provider: provider as ProviderCredential["provider"],
        label: (body.label as string | null) ?? null,
        masked_key: `${BULLETS}${key.slice(-4)}`,
      });
      rows.push(row);
      return jsonResponse({ ...row }, 201);
    }
    if (url.endsWith("/ai/providers") && method === "GET") {
      if (overrides.list !== undefined) return overrides.list();
      return jsonResponse(rows.map((row) => ({ ...row })));
    }
    return errorResponse("bad_response", 500);
  }

  const store = {
    requests,
    overrides,
    verified: true,
    setTestVerdict(verdict: ProviderTestResult) {
      testVerdict = verdict;
    },
    listGets() {
      return requests.filter(
        (request) => request.url.endsWith("/ai/providers") && request.method === "GET",
      );
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(input, init)),
  );
  return store;
}

function renderScreen() {
  render(
    <AuthProvider>
      <SettingsScreen />
    </AuthProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("SettingsScreen load states", () => {
  it("renders providers with a clean heading outline", async () => {
    const store = createStore([
      credential(),
      credential({ id: "cred-openai", provider: "openai", label: null }),
    ]);
    let release!: (response: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    store.overrides.list = () => gate;
    renderScreen();

    expect(await screen.findByLabelText("Loading settings")).toBeDefined();
    release(
      jsonResponse([
        credential(),
        credential({ id: "cred-openai", provider: "openai", label: null }),
      ]),
    );
    // The h1 paints before the list resolves — sync on the last row, then assert the outline.
    expect(await screen.findByRole("heading", { name: "OpenAI", level: 3 })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Settings", level: 1 })).toBeDefined();
    expect(screen.getByRole("heading", { name: "AI providers", level: 2 })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Groq", level: 3 })).toBeDefined();
  });

  it("shows the session-gone nudge when the session is dead on load", async () => {
    const store = createStore([credential()]);
    store.overrides.list = () => errorResponse("unauthenticated", 401);
    renderScreen();

    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("Session expired");
    expect(screen.getByRole("link", { name: "Sign in" })).toBeDefined();
  });

  it("shows a retryable error when loading fails", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    store.overrides.list = () => errorResponse("internal_error", 500);
    renderScreen();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn't load your settings");
    expect(alert.textContent).toContain("Something went wrong. Please try again.");
    store.overrides.list = undefined;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Groq", level: 3 })).toBeDefined();
  });

  it("rejects wrong-shaped lists instead of rendering garbage", async () => {
    const store = createStore([credential()]);
    store.overrides.list = () => jsonResponse({ items: [] });
    renderScreen();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The service returned an unexpected response.");
  });

  it("allows unconfirmed accounts to access settings", async () => {
    const store = createStore([credential()]);
    store.verified = false;
    renderScreen();
    expect(await screen.findByText("AI providers")).toBeDefined();
    expect(store.listGets()).toHaveLength(1);
  });
});

describe("SettingsScreen empty state", () => {
  it("explains optional AI without pressure and opens the dialog", async () => {
    const user = userEvent.setup();
    createStore([]);
    renderScreen();

    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("No AI providers yet");
    expect(status.textContent).toContain("work without any provider");
    expect(status.textContent).toContain("encrypted before storage");
    expect(screen.queryByRole("button", { name: "Add provider" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Add your first provider" }));
    expect(screen.getByRole("dialog", { name: "Add provider" })).toBeDefined();
  });
});

describe("SettingsScreen add flow", () => {
  async function openAdd() {
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add provider" }));
    return user;
  }

  it("offers the six canonical providers with configured ones marked", async () => {
    createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });
    await openAdd();

    const select = screen.getByLabelText("Provider") as HTMLSelectElement;
    const options = [...select.options].map((option) => ({
      value: option.value,
      text: option.text,
      disabled: option.disabled,
    }));
    expect(options.map((option) => option.value)).toEqual([
      "",
      "gemini",
      "groq",
      "openai",
      "anthropic",
      "openrouter",
      "huggingface",
    ]);
    expect(options.find((option) => option.value === "groq")).toMatchObject({
      text: "Groq (already configured)",
      disabled: true,
    });
    expect(options.find((option) => option.value === "openai")).toMatchObject({
      text: "OpenAI",
      disabled: false,
    });
  });

  it("validates provider and key client-side before any request", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    await user.click(screen.getByRole("button", { name: "Save credential" }));
    expect(screen.getByText("Choose a provider.")).toBeDefined();
    expect(screen.getByText("Enter your API key.")).toBeDefined();
    expect(store.requests.filter((request) => request.method === "POST")).toHaveLength(0);

    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.type(screen.getByLabelText("API key"), "abc");
    await user.click(screen.getByRole("button", { name: "Save credential" }));
    expect(screen.getByText("API keys are between 4 and 2,000 characters.")).toBeDefined();
    expect(store.requests.filter((request) => request.method === "POST")).toHaveLength(0);
  });

  it("creates, refetches, announces, and starts fresh next time", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.type(screen.getByLabelText("Label (optional)"), "Personal");
    await user.type(screen.getByLabelText("API key"), "sk-test-key-9999");
    await user.click(screen.getByRole("button", { name: "Save credential" }));

    const notice = await screen.findByText(/OpenAI credential saved/);
    expect(notice.textContent).toContain("won't be shown again");
    const posts = store.requests.filter((request) => request.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual({
      provider: "openai",
      label: "Personal",
      api_key: "sk-test-key-9999",
    });
    // Server-confirmed: the list was re-read (initial + post-create).
    await waitFor(() => expect(store.listGets()).toHaveLength(2));
    expect(screen.getByRole("heading", { name: "OpenAI", level: 3 })).toBeDefined();
    expect(screen.queryByRole("dialog")).toBeNull();

    // Reopening starts blank — nothing retained from the last save.
    await user.click(screen.getByRole("button", { name: "Add provider" }));
    expect((screen.getByLabelText("API key") as HTMLInputElement).value).toBe("");
  });

  it("keeps the dialog open with code copy on conflict", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    store.overrides.create = () => errorResponse("conflict", 409);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    await user.selectOptions(screen.getByLabelText("Provider"), "groq");
    await user.type(screen.getByLabelText("API key"), "gsk-key-1111");
    await user.click(screen.getByRole("button", { name: "Save credential" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Replace the existing key");
    expect(screen.getByRole("dialog", { name: "Add provider" })).toBeDefined();
    expect(store.listGets()).toHaveLength(1); // no refetch — nothing was saved
  });

  it("maps server field errors onto fields", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    store.overrides.create = () =>
      jsonResponse(
        {
          error: {
            code: "validation_error",
            message: "Request validation failed.",
            details: [{ loc: ["body", "label"], msg: "String too long" }],
          },
        },
        400,
      );
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    await user.selectOptions(screen.getByLabelText("Provider"), "groq");
    await user.type(screen.getByLabelText("API key"), "gsk-key-1111");
    await user.click(screen.getByRole("button", { name: "Save credential" }));

    expect(await screen.findByText("Keep the label under 80 characters.")).toBeDefined();
  });

  it("clears the secret but keeps safe selections when the session dies mid-save", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    store.overrides.create = () => errorResponse("unauthenticated", 401);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    await user.selectOptions(screen.getByLabelText("Provider"), "groq");
    await user.type(screen.getByLabelText("Label (optional)"), "Work");
    await user.type(screen.getByLabelText("API key"), "gsk-key-1111");
    await user.click(screen.getByRole("button", { name: "Save credential" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Session expired");
    expect(screen.getByRole("link", { name: "Sign in again" })).toBeDefined();
    expect((screen.getByLabelText("API key") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Provider") as HTMLSelectElement).value).toBe("groq");
    expect((screen.getByLabelText("Label (optional)") as HTMLInputElement).value).toBe("Work");
  });

  it("reveals the key only deliberately, with an honest toggle", async () => {
    const user = userEvent.setup();
    createStore([]);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    const field = screen.getByLabelText("API key") as HTMLInputElement;
    expect(field.type).toBe("password");
    const toggle = screen.getByRole("button", { name: "Show API key" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    await user.click(toggle);
    expect(field.type).toBe("text");
    const hide = screen.getByRole("button", { name: "Hide API key" });
    expect(hide.getAttribute("aria-pressed")).toBe("true");
    await user.click(hide);
    expect(field.type).toBe("password");
  });

  it("Escape and Cancel close without saving", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    const cta = screen.getByRole("button", { name: "Add your first provider" });

    await user.click(cta);
    expect(screen.getByRole("dialog", { name: "Add provider" })).toBeDefined();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(cta);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(cta);
    expect(store.requests.filter((request) => request.method === "POST")).toHaveLength(0);
  });
});

describe("SettingsScreen replace-key flow", () => {
  it("shows the masked value as information with a blank secret field", async () => {
    const user = userEvent.setup();
    createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Replace key" }));
    const dialog = screen.getByRole("dialog", { name: "Replace Groq key" });
    expect(within(dialog).getByText(`${BULLETS}1234`)).toBeDefined();
    expect((within(dialog).getByLabelText("New API key") as HTMLInputElement).value).toBe("");
    // The masked server value is never an editable secret (password inputs
    // carry no textbox role, so query the fields directly).
    for (const input of dialog.querySelectorAll("input")) {
      expect(input.value).not.toContain("•");
    }
  });

  it("replaces, announces, and refetches the new mask", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Replace key" }));
    const dialog = screen.getByRole("dialog", { name: "Replace Groq key" });
    await user.type(within(dialog).getByLabelText("New API key"), "gsk-brand-new-7777");
    await user.click(within(dialog).getByRole("button", { name: "Replace key" }));
    expect(await screen.findByText("Groq key replaced.")).toBeDefined();
    const rotates = store.requests.filter((request) => request.url.includes("/rotate-key"));
    expect(rotates).toHaveLength(1);
    expect(rotates[0]?.body).toEqual({ api_key: "gsk-brand-new-7777" });
    await waitFor(() => expect(store.listGets()).toHaveLength(2));
    expect(screen.getByText(`${BULLETS}7777`)).toBeDefined();
  });

  it("surfaces already-stored conflicts without closing", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    store.overrides.rotate = () => errorResponse("conflict", 409);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Replace key" }));
    const dialog = screen.getByRole("dialog", { name: "Replace Groq key" });
    await user.type(within(dialog).getByLabelText("New API key"), "gsk-brand-new-7777");
    await user.click(within(dialog).getByRole("button", { name: "Replace key" }));
    expect(
      await screen.findByText("That key is already stored on another credential."),
    ).toBeDefined();
    expect(screen.getByRole("dialog", { name: "Replace Groq key" })).toBeDefined();
  });
});

describe("SettingsScreen delete flow", () => {
  it("focuses the safe default; Cancel closes and refocuses the trigger", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    const trigger = screen.getByRole("button", { name: "Remove" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Remove Groq?" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(within(dialog).getByText(/cannot be undone/)).toBeDefined();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Keep credential" }));

    await user.click(screen.getByRole("button", { name: "Keep credential" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(store.requests.filter((request) => request.method === "DELETE")).toHaveLength(0);
  });

  it("Escape cancels without calling the API", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(store.requests.filter((request) => request.method === "DELETE")).toHaveLength(0);
  });

  it("traps Tab between the dialog buttons", async () => {
    const user = userEvent.setup();
    createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Remove" }));
    const keep = screen.getByRole("button", { name: "Keep credential" });
    const confirm = screen.getByRole("button", { name: "Remove credential" });
    expect(document.activeElement).toBe(keep);
    const close = screen.getByRole("button", { name: "Close dialog" });
    await user.tab();
    expect(document.activeElement).toBe(confirm);
    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(confirm);
  });

  it("removes on confirm with pending state, then announces and refetches", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    let release!: (response: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    store.overrides.remove = () => gate;
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Remove credential" }));
    expect(screen.getByRole("button", { name: "Removing…" })).toHaveProperty("disabled", true);
    // The gated override bypasses the store's default row removal — the
    // post-delete refetch reads the emptied list instead.
    store.overrides.list = () => jsonResponse([]);
    release(new Response(null, { status: 204 }));

    expect(await screen.findByText("Groq credential removed.")).toBeDefined();
    await waitFor(() => expect(store.listGets()).toHaveLength(2));
    expect(screen.queryByRole("heading", { name: "Groq", level: 3 })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("treats already-gone as success (other tab removed it)", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    store.overrides.remove = () => errorResponse("ai_provider_not_found", 404);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Remove credential" }));
    expect(await screen.findByText("Groq credential removed.")).toBeDefined();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("stays open with code copy on failure (session-aware)", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    store.overrides.remove = () => errorResponse("internal_error", 500);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Remove credential" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Something went wrong. Please try again.");
    expect(screen.getByRole("dialog", { name: "Remove Groq?" })).toBeDefined();
    expect(screen.queryByRole("link", { name: "Sign in again" })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers the sign-in nudge when the session dies mid-delete", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    store.overrides.remove = () => errorResponse("unauthenticated", 401);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Remove credential" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Your session has expired.");
    expect(screen.getByRole("link", { name: "Sign in again" })).toBeDefined();
  });
});

describe("SettingsScreen server truth", () => {
  it("refetches after enable/disable and announces the outcome", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("switch", { name: "Disable Groq" }));
    expect(await screen.findByText("Groq disabled.")).toBeDefined();
    await waitFor(() => expect(store.listGets()).toHaveLength(2));
    const chips = within(screen.getByRole("list", { name: "Groq status" }));
    expect(chips.getByText("Disabled")).toBeDefined();
  });

  it("refetches after a default claim so the move is server-confirmed", async () => {
    const user = userEvent.setup();
    const store = createStore([
      credential({ id: "cred-groq", provider: "groq", is_default: true }),
      credential({ id: "cred-openai", provider: "openai", label: null, is_default: false }),
    ]);
    renderScreen();
    await screen.findByRole("heading", { name: "OpenAI", level: 3 });

    const openaiCard = screen.getByRole("heading", { name: "OpenAI", level: 3 }).closest("article");
    expect(openaiCard).not.toBeNull();
    await user.click(
      within(openaiCard as HTMLElement).getByRole("button", { name: "Set as default" }),
    );
    expect(await screen.findByText("OpenAI is now the default provider.")).toBeDefined();
    await waitFor(() => expect(store.listGets()).toHaveLength(2));
    expect(screen.getAllByText("Default")).toHaveLength(1);
  });

  it("keeps stale rows behind an honest notice when the refresh fails", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    let gets = 0;
    store.overrides.list = () => {
      gets += 1;
      return errorResponse("internal_error", 500);
    };
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    await screen.findByText(/Connection works/);
    expect(await screen.findByText(/couldn't be refreshed/)).toBeDefined();
    expect(gets).toBe(1);
    // The stale card stays (honest), the verdict still shows (it succeeded).
    expect(screen.getByRole("heading", { name: "Groq", level: 3 })).toBeDefined();
  });

  it("transitions to session-gone when the refresh proves the session dead", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    store.overrides.list = () => errorResponse("unauthenticated", 401);
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    // The verdict may never paint: the dead-session refetch unmounts the
    // card behind the standard session-gone panel (verdict rendering itself
    // is covered by the card tests + the stale-refresh test above).
    expect(await screen.findByText("Sign in again to manage your settings.")).toBeDefined();
  });
});

describe("SettingsScreen secret lifecycle", () => {
  it("never writes secrets to browser storage during a full add journey", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    createStore([]);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });

    await user.click(screen.getByRole("button", { name: "Add your first provider" }));
    await user.selectOptions(screen.getByLabelText("Provider"), "groq");
    await user.type(screen.getByLabelText("API key"), "gsk-live-secret-material");
    await user.click(screen.getByRole("button", { name: "Show API key" }));
    await user.click(screen.getByRole("button", { name: "Save credential" }));
    await screen.findByText(/Groq credential saved/);

    expect(setItem).not.toHaveBeenCalled();
    expect(document.body.innerHTML).not.toContain("gsk-live-secret-material");
  });

  it("never puts keys in URLs and never calls providers directly", async () => {
    const user = userEvent.setup();
    const store = createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("button", { name: "Replace key" }));
    const dialog = screen.getByRole("dialog", { name: "Replace Groq key" });
    await user.type(within(dialog).getByLabelText("New API key"), "gsk-direct-call-proof");
    await user.click(within(dialog).getByRole("button", { name: "Replace key" }));
    await screen.findByText("Groq key replaced.");
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    await screen.findByText(/Connection works/);

    for (const request of store.requests) {
      expect(request.url.startsWith("http://localhost:8000/api/v1/")).toBe(true);
      expect(request.url).not.toContain("gsk-direct-call-proof");
    }
  });
});

describe("SettingsScreen keyboard and announcements", () => {
  it("toggles the enable switch from the keyboard", async () => {
    const user = userEvent.setup();
    createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    const enable = screen.getByRole("switch", { name: "Disable Groq" });
    enable.focus();
    await user.keyboard(" ");
    expect(await screen.findByText("Groq disabled.")).toBeDefined();
  });

  it("announces confirmations through a dismissible status region", async () => {
    const user = userEvent.setup();
    createStore([credential()]);
    renderScreen();
    await screen.findByRole("heading", { name: "Groq", level: 3 });

    await user.click(screen.getByRole("switch", { name: "Disable Groq" }));
    const notice = await screen.findByText("Groq disabled.");
    expect(notice.closest("[role='status']")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByText("Groq disabled.")).toBeNull();
  });

  it("associates every dialog control with its label", async () => {
    const user = userEvent.setup();
    createStore([]);
    renderScreen();
    await screen.findByRole("button", { name: "Add your first provider" });
    await user.click(screen.getByRole("button", { name: "Add your first provider" }));

    const dialog = screen.getByRole("dialog", { name: "Add provider" });
    expect((within(dialog).getByLabelText("Provider") as HTMLSelectElement).value).toBe("");
    expect(within(dialog).getByLabelText("Label (optional)")).toBeDefined();
    expect(within(dialog).getByLabelText("API key")).toBeDefined();
  });
});

describe("SettingsScreen account sections (Stage 16)", () => {
  it("renders profile with email read-only and the saved display name", async () => {
    createStore([]);
    renderScreen();
    // The input only exists once the profile GET resolves — sync on it first.
    const input = (await screen.findByLabelText("Display name")) as HTMLInputElement;
    expect(input.value).toBe("Ada");
    const section = screen.getByRole("region", { name: "Profile" });
    expect(within(section).getByText("ada@example.com")).toBeDefined();
  });

  it("saves the display name and confirms from the server row", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    renderScreen();
    const input = (await screen.findByLabelText("Display name")) as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "  Grace Hopper  ");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Profile saved.")).toBeDefined();
    const patch = store.requests.find(
      (request) => request.url.endsWith("/settings/profile") && request.method === "PATCH",
    );
    // Client-side trim: the server also normalizes, but we never send padding.
    expect(patch?.body).toEqual({ display_name: "Grace Hopper" });
    expect((screen.getByLabelText("Display name") as HTMLInputElement).value).toBe("Grace Hopper");
  });

  it("mounts the password form as its own section", async () => {
    createStore([]);
    renderScreen();
    expect(await screen.findByRole("heading", { name: "Password", level: 2 })).toBeDefined();
    expect(screen.getByRole("form", { name: "Change password" })).toBeDefined();
  });

  it("privacy section wires retention, export, and purge controls to real endpoints", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    renderScreen();
    const section = await screen.findByRole("region", { name: "Privacy" });
    expect(within(section).getByRole("link", { name: "History" })).toBeDefined();
    expect(within(section).getByText(/never includes passwords, session tokens/)).toBeDefined();

    await user.type(within(section).getByLabelText("Automatic history retention"), "30");
    await user.click(within(section).getByRole("button", { name: "Save retention" }));
    expect(await within(section).findByText(/set to 30 days/)).toBeDefined();

    await user.click(within(section).getByRole("button", { name: "Create export link" }));
    const exportLink = await within(section).findByRole("link", {
      name: "Download privacy export",
    });
    expect(exportLink.getAttribute("href")).toContain("/api/v1/privacy/export/export-token");

    await user.clear(within(section).getByLabelText("Purge old history now"));
    await user.type(within(section).getByLabelText("Purge old history now"), "45");
    await user.click(within(section).getByRole("button", { name: "Purge old history" }));
    expect(
      await within(section).findByText(/Purged 2 analyses and 1 stored documents/),
    ).toBeDefined();

    expect(
      store.requests.some(
        (request) => request.url.endsWith("/settings/privacy") && request.method === "GET",
      ),
    ).toBe(true);
    expect(
      store.requests.find(
        (request) => request.url.endsWith("/settings/privacy") && request.method === "PATCH",
      )?.body,
    ).toEqual({ history_retention_days: 30 });
    expect(
      store.requests.some(
        (request) => request.url.endsWith("/privacy/export") && request.method === "POST",
      ),
    ).toBe(true);
    expect(
      store.requests.find(
        (request) => request.url.endsWith("/privacy/purge-history") && request.method === "POST",
      )?.body,
    ).toEqual({ older_than_days: 45 });
  });

  it("deletes the account only after typing DELETE, then shows the farewell", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    renderScreen();
    expect(await screen.findByRole("heading", { name: "Delete account", level: 2 })).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Delete my account…" }));
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    expect(within(dialog).getByText("ada@example.com")).toBeDefined();
    const confirm = within(dialog).getByRole("button", { name: "Delete account" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELET");
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "E");
    expect((confirm as HTMLButtonElement).disabled).toBe(false);
    await user.click(confirm);
    expect(await screen.findByRole("heading", { name: "Account deleted", level: 1 })).toBeDefined();
    expect(screen.getByRole("link", { name: "Create a new account" })).toBeDefined();
    const call = store.requests.find(
      (request) => request.url.endsWith("/auth/account") && request.method === "DELETE",
    );
    expect(call?.body).toEqual({ confirmation: "DELETE" });
    // The protected tree is gone — no provider rows, no profile form behind it.
    expect(screen.queryByRole("heading", { name: "AI providers" })).toBeNull();
  });

  it("keeps the delete dialog open with mapped copy when the server refuses", async () => {
    const user = userEvent.setup();
    const store = createStore([]);
    store.overrides.deleteAccount = () => errorResponse("rate_limited", 429);
    renderScreen();
    await screen.findByRole("heading", { name: "Delete account", level: 2 });
    await user.click(screen.getByRole("button", { name: "Delete my account…" }));
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    await user.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(within(dialog).getByRole("button", { name: "Delete account" }));
    expect(
      await within(dialog).findByText("Too many attempts. Please try again later."),
    ).toBeDefined();
    expect(screen.getByRole("dialog", { name: "Delete your account?" })).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Account deleted" })).toBeNull();
  });
});
