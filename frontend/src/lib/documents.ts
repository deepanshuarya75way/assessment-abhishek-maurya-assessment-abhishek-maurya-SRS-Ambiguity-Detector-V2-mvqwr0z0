/**
 * Document API layer — the ONLY module that talks to `/documents/*`. Built
 * exclusively on the canonical client (`apiForm` for the multipart upload,
 * `api` for reads): cookies flow via `credentials: "include"` and session
 * tokens never touch JS.
 *
 * Uploads silent-refresh a stale session exactly like `createAnalysis`: a
 * 401 means "not executed" (the guard rejects before the service runs), so
 * the single retry cannot double-create.
 */

import type {
  DocumentDownloadUrl,
  DocumentMetadata,
  DocumentUploadResponse,
  ListDocumentsParams,
} from "../types/documents";

import { api, apiBaseUrl, apiForm, type Collection } from "./api";
import { withSessionRetry } from "./auth";

/** Server limits mirrored for instant client feedback (server authoritative). */
export const UPLOAD_LIMITS = {
  maxBytes: 10 * 1024 * 1024,
  maxTitle: 200,
  extensions: [".pdf", ".docx", ".txt"],
} as const;

/**
 * Upload backstop (ms). The server budgets 60 s for validate+extract (then
 * an honest 503 arrives promptly) — this only guards a truly hung
 * connection, so it sits well above: streaming + processing + analysis of
 * a large file, with headroom.
 */
export const UPLOAD_TIMEOUT_MS = 180_000;

export interface UploadDocumentInput {
  file: File;
  title: string;
  /** Opt into the shared post-commit AI step (Stage 14 — same vocabulary as
   * the text path). Sent explicitly: the server defaults to false. */
  aiEnhance: boolean;
}

/**
 * Upload one SRS file (pdf/docx/txt) → validate → extract → run the SAME
 * deterministic pipeline as pasted text. Blank titles are omitted so the
 * server falls back to the filename.
 */
export function uploadDocument(input: UploadDocumentInput): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("files", input.file, input.file.name);
  const title = input.title.trim();
  if (title !== "") form.append("title", title.slice(0, UPLOAD_LIMITS.maxTitle));
  form.append("ai_enhance", input.aiEnhance ? "true" : "false");
  return withSessionRetry(() =>
    apiForm<DocumentUploadResponse>("/documents/upload", form, {
      timeoutMs: UPLOAD_TIMEOUT_MS,
    }),
  );
}

/** Fetch one owned document's metadata (404 unless owned — IDOR rule). */
export function getDocument(id: string): Promise<DocumentMetadata> {
  return withSessionRetry(() => api<DocumentMetadata>(`/documents/${id}`));
}

/** Newest-first page of owned documents (contract §3; server clamps paging). */
export function listDocuments(
  params: ListDocumentsParams = {},
): Promise<Collection<DocumentMetadata>> {
  const search = new URLSearchParams();
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.page_size !== undefined) search.set("page_size", String(params.page_size));
  const query = search.size > 0 ? `?${search.toString()}` : "";
  return withSessionRetry(() => api<Collection<DocumentMetadata>>(`/documents${query}`));
}

/** Purge one owned document (row + stored binary). 204 → void. */
export function deleteDocument(id: string): Promise<void> {
  return withSessionRetry(() => api<void>(`/documents/${id}`, { method: "DELETE" }));
}

/**
 * Mint a short-lived signed download URL (Stage 19). POST (not GET): minting
 * issues a bearer credential, so it rides the verified + CSRF + tight-bucket
 * guard. Retry-safe: the guard rejects pre-execution on 401.
 */
export function mintDocumentDownloadUrl(id: string): Promise<DocumentDownloadUrl> {
  return withSessionRetry(() =>
    api<DocumentDownloadUrl>(`/documents/${id}/download-url`, { method: "POST" }),
  );
}

/**
 * Resolve a minted API-relative download path to the absolute URL the
 * browser navigates to (the SPA origin and the API origin differ). The path
 * already carries the `/api/v1` prefix, so it resolves against the API
 * ORIGIN (a naive base + path join would double the prefix). Pure — no
 * fetch, no token handling.
 */
export function resolveDownloadUrl(path: string): string {
  return new URL(path, apiBaseUrl()).toString();
}

/** Human file size for the picker/dropzone (1 decimal under 100 units). */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"] as const;
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

/** Lowercased suffix check — instant feedback only, the server re-verifies. */
export function hasAllowedExtension(name: string): boolean {
  const dot = name.lastIndexOf(".");
  if (dot < 0) return false;
  const suffix = name.slice(dot).toLowerCase();
  return (UPLOAD_LIMITS.extensions as readonly string[]).includes(suffix);
}
