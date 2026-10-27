/**
 * Document domain types — mirrored from the project contract
 * (Stage 08: upload+analyze; metadata only — the binary and the storage
 * key are never exposed to clients). Backend: `app/schemas/documents.py`.
 * Same names, same optionality.
 */

import type { AnalysisResult } from "./analysis";

/** Verified file type (server-proved: extension + MIME + magic bytes). */
export type DocumentFileType = "pdf" | "docx" | "txt";

/** Extraction outcome. `pending`/`failed` are future async states. */
export type DocumentExtractionStatus = "pending" | "ok" | "failed";

/** One owned upload's metadata (GET result + upload-response half). */
export interface DocumentMetadata {
  id: string;
  filename: string;
  file_type: DocumentFileType;
  mime_type: string;
  byte_size: number;
  sha256: string;
  extracted_chars: number;
  extraction_status: DocumentExtractionStatus;
  created_at: string;
}

/** POST /documents/upload result: the stored file + its full analysis. */
export interface DocumentUploadResponse {
  document: DocumentMetadata;
  analysis: AnalysisResult;
}

/** GET /documents paging (newest-first, no filters in v1). */
export interface ListDocumentsParams {
  page?: number;
  page_size?: number;
}

/**
 * POST /documents/{id}/download-url result (Stage 19). `download_url` is an
 * API-relative path (carries the `/api/v1` prefix) — resolve it against the
 * API origin (see `resolveDownloadUrl`) before navigating. The embedded
 * token is a short-lived single-document bearer: never log or store it.
 */
export interface DocumentDownloadUrl {
  download_url: string;
  expires_at: string;
}
