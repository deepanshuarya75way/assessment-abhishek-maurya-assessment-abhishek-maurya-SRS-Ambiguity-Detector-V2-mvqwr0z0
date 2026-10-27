import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, api } from "./api";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ status: "ok" })),
    );
    await expect(api<{ status: string }>("/health/live")).resolves.toEqual({ status: "ok" });
  });

  it("sends cookies with a JSON body", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    await api("/echo", { method: "POST", body: { a: 1 } });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/echo"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ a: 1 }),
      }),
    );
  });

  it("throws ApiRequestError with the envelope code on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { code: "not_found", message: "Nope." } }, 404)),
    );
    const err = await api("/missing").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as ApiRequestError).code).toBe("not_found");
    expect((err as ApiRequestError).status).toBe(404);
  });

  it("resolves undefined on 204 No Content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    await expect(api<void>("/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("maps network failure to network_unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    const err = await api("/health/live").catch((e: unknown) => e);
    expect((err as ApiRequestError).code).toBe("network_unreachable");
    expect((err as ApiRequestError).status).toBe(0);
  });

  it("maps timeout to request_timeout", async () => {
    // Faithful stub: like real fetch, rejects with TimeoutError when aborted.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("The operation timed out.", "TimeoutError"));
            });
          }),
      ),
    );
    const err = await api("/slow", { timeoutMs: 20 }).catch((e: unknown) => e);
    expect((err as ApiRequestError).code).toBe("request_timeout");
  });
});
