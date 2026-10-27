/**
 * Analysis error-code → user-facing copy (the project contract: the frontend
 * switches on `code`, NEVER on `message`). Server strings are never displayed.
 * Field-detail traversal is shared with `lib/auth-errors.ts` (no duplication).
 */

import { ApiRequestError } from "./api";
import { validationFieldErrors } from "./auth-errors";

const GENERIC_FALLBACK = "Something went wrong. Please try again.";

export function analysisErrorMessage(err: unknown): string {
  if (!(err instanceof ApiRequestError)) return GENERIC_FALLBACK;
  switch (err.code) {
    case "no_requirements_detected":
      return "We couldn't find any requirements in that text. Numbered, bulleted, or ID-tagged statements (with words like “shall” or “must”) segment best.";
    case "text_too_large":
      return "That input produced more requirements than a single analysis can hold. Split it into smaller parts and analyze each one.";
    case "document_analysis_unavailable":
      return "Re-analyzing a saved document is not available yet. Upload the file to analyze it.";
    case "unsupported_file_type":
      return "That file is not a readable PDF, DOCX, or TXT document. Renamed files (for example a spreadsheet saved as .txt) are rejected too.";
    case "empty_file":
      return "That file is empty, so there is nothing to analyze.";
    case "file_too_large":
      return "That file is larger than 10 MB. Split it into smaller parts and upload one at a time.";
    case "extracted_text_too_large":
      return "That document holds more text than a single analysis can take. Split it into smaller parts.";
    case "extraction_failed":
      return "We could not read that document. The file may be corrupt, so try re-exporting it.";
    case "no_extractable_text":
      return "We could not find any text in that document. Scanned or image-only PDFs are not supported yet.";
    case "too_many_files":
      return "Upload one file at a time.";
    case "document_processing_timeout":
      return "Processing took too long. Try a smaller file, or try again.";
    case "document_not_found":
      return "That document does not exist or belongs to a different account.";
    case "analysis_not_found":
      return "That analysis doesn't exist or belongs to a different account.";
    case "validation_error":
      return "Please check your input and try again.";
    case "unauthenticated":
      return "Your session has expired. Please log in again.";
    case "rate_limited":
      return "Too many requests. Please wait a moment and try again.";
    case "forbidden":
      return "You don't have permission to do that.";
    case "network_unreachable":
    case "request_timeout":
    case "bad_response":
      // Our own client's codes — messages are safe by construction (lib/api.ts).
      return err.message;
    default:
      return GENERIC_FALLBACK;
  }
}

/** Backend field names the analyzer maps `validation_error` details onto. */
const ANALYSIS_FIELDS = {
  known: new Set(["title", "text"]),
  copy: {
    title: "Keep the title under 200 characters.",
    text: "Keep your SRS under 200,000 characters.",
  } as Record<string, string>,
};

/**
 * Extract per-field errors from an analysis `validation_error` envelope.
 * Unknown shapes → {} (same contract as the auth variant).
 */
export function analysisFieldErrors(err: unknown): Partial<Record<string, string>> {
  return validationFieldErrors(err, ANALYSIS_FIELDS);
}
