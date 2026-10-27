import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProviderCredential, ProviderTestResult } from "../types/providers";
import { ApiRequestError } from "./api";
import {
  createProvider,
  deleteProvider,
  listProviders,
  rotateProviderKey,
  testProvider,
  updateProvider,
} from "./providers";

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
    id: "cred-1",
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("provider API layer", () => {
  it("lists credentials with a plain GET", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([credential()]));
    vi.stubGlobal("fetch", fetchMock);
    await expect(listProviders()).resolves.toEqual([credential()]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/ai/providers"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("creates with the key in the JSON body (never the URL)", async () => {
    const seen: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        seen.push({ url: String(input), init });
        return jsonResponse(credential());
      }),
    );
    await createProvider({ provider: "groq", label: "Work", api_key: "gsk-secret" });
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe("http://localhost:8000/api/v1/ai/providers");
    expect(seen[0]?.url).not.toContain("gsk-secret");
    expect(seen[0]?.init?.method).toBe("POST");
    expect(seen[0]?.init?.body).toBe(
      JSON.stringify({ provider: "groq", label: "Work", api_key: "gsk-secret" }),
    );
  });

  it("patches metadata by id", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(credential({ is_default: true })));
    vi.stubGlobal("fetch", fetchMock);
    const row = await updateProvider("cred-1", { is_default: true });
    expect(row.is_default).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/ai/providers/cred-1"),
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ is_default: true }) }),
    );
  });

  it("rotates with the new key in the JSON body (never the URL)", async () => {
    const seen: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        seen.push({ url: String(input), init });
        return jsonResponse(credential());
      }),
    );
    await rotateProviderKey("cred-1", { api_key: "gsk-rotated" });
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toContain("/ai/providers/cred-1/rotate-key");
    expect(seen[0]?.url).not.toContain("gsk-rotated");
    expect(seen[0]?.init?.method).toBe("POST");
  });

  it("tests a stored credential and decodes the verdict", async () => {
    const verdict: ProviderTestResult = {
      ok: true,
      models: ["m1"],
      latency_ms: 12,
      error: null,
    };
    const fetchMock = vi.fn(async () => jsonResponse(verdict));
    vi.stubGlobal("fetch", fetchMock);
    await expect(testProvider("cred-1")).resolves.toEqual(verdict);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/ai/providers/cred-1/test"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("deletes by id and resolves void on 204", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(deleteProvider("cred-1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/ai/providers/cred-1"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("propagates envelope codes (conflict, not-found, rate limit)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse("conflict", 409)),
    );
    const conflicted = await createProvider({
      provider: "groq",
      api_key: "gsk-x",
    }).catch((err: unknown) => err);
    expect(conflicted).toBeInstanceOf(ApiRequestError);
    expect((conflicted as ApiRequestError).code).toBe("conflict");

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse("ai_provider_not_found", 404)),
    );
    const missing = await testProvider("gone").catch((err: unknown) => err);
    expect((missing as ApiRequestError).code).toBe("ai_provider_not_found");

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse("rate_limited", 429)),
    );
    const limited = await testProvider("cred-1").catch((err: unknown) => err);
    expect((limited as ApiRequestError).code).toBe("rate_limited");
  });

  it("retries once after a silent refresh on 401, then stands on the second", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        calls.push(url);
        if (url.includes("/auth/refresh")) return jsonResponse({ ok: true });
        if (url.includes("/ai/providers") && !url.includes("/auth/")) {
          return calls.filter((call) => call.includes("/ai/providers")).length > 1
            ? jsonResponse([credential()])
            : errorResponse("unauthenticated", 401);
        }
        return errorResponse("unauthenticated", 401);
      }),
    );
    await expect(listProviders()).resolves.toEqual([credential()]);
    expect(calls.filter((call) => call.includes("/ai/providers"))).toHaveLength(2);
    expect(calls.some((call) => call.includes("/auth/refresh"))).toBe(true);
  });
});
