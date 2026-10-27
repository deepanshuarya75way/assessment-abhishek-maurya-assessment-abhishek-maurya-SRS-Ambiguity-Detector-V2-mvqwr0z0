import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentDownloadUrl, DocumentMetadata } from "../types/documents";
import {
  deleteDocument,
  listDocuments,
  mintDocumentDownloadUrl,
  resolveDownloadUrl,
  uploadDocument,
} from "./documents";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function metadata(overrides: Partial<DocumentMetadata> = {}): DocumentMetadata {
  return {
    id: "doc-1",
    filename: "srs.txt",
    file_type: "txt",
    mime_type: "text/plain",
    byte_size: 42,
    sha256: "ab".repeat(32),
    extracted_chars: 42,
    extraction_status: "ok",
    created_at: "2026-09-24T00:00:00+00:00",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("document API layer", () => {
  it("uploads multipart to /documents/upload (file + title + ai flag)", async () => {
    const seen: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        seen.push({ url: String(input), init });
        return jsonResponse({ document: metadata(), analysis: {} });
      }),
    );
    const file = new File(["FR-001: hi.\n"], "srs.txt", { type: "text/plain" });
    await uploadDocument({ file, title: "Sprint SRS", aiEnhance: true });
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toContain("/documents/upload");
    const form = seen[0]?.init?.body as FormData;
    expect(form.get("title")).toBe("Sprint SRS");
    expect(form.get("ai_enhance")).toBe("true");
    expect((form.get("files") as File).name).toBe("srs.txt");
  });

  it("lists with a plain GET (no query by default)", async () => {
    const page = { items: [metadata()], page: 1, page_size: 20, total: 1 };
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        seen.push(String(input));
        return jsonResponse(page);
      }),
    );
    await expect(listDocuments()).resolves.toEqual(page);
    expect(seen).toHaveLength(1);
    expect(seen[0]).toContain("/documents");
    expect(seen[0]).not.toContain("?");
  });

  it("lists with paging params when given", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        seen.push(String(input));
        return jsonResponse({ items: [], page: 2, page_size: 5, total: 0 });
      }),
    );
    await listDocuments({ page: 2, page_size: 5 });
    expect(seen).toHaveLength(1);
    expect(seen[0]).toContain("page=2");
    expect(seen[0]).toContain("page_size=5");
  });

  it("deletes with DELETE (204 → void)", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(deleteDocument("doc-1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/documents/doc-1"),
      expect.objectContaining({ method: "DELETE", credentials: "include" }),
    );
  });

  it("mints download URLs with POST (never GET — minting issues a bearer)", async () => {
    const minted: DocumentDownloadUrl = {
      download_url: "/api/v1/documents/doc-1/download?token=abc",
      expires_at: "2026-09-24T00:15:00+00:00",
    };
    const fetchMock = vi.fn(async () => jsonResponse(minted));
    vi.stubGlobal("fetch", fetchMock);
    await expect(mintDocumentDownloadUrl("doc-1")).resolves.toEqual(minted);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/documents/doc-1/download-url"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("resolves minted paths against the API origin (no doubled prefix, no fetch)", () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    expect(resolveDownloadUrl("/api/v1/documents/doc-1/download?token=abc")).toBe(
      "http://localhost:8000/api/v1/documents/doc-1/download?token=abc",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
