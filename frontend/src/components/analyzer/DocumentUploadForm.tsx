"use client";

/**
 * SRS file upload + analysis submit (Stage 08: uploading runs the SAME
 * pipeline as pasted text — validate, extract, segment, detect, score).
 * Dropzone + file picker for exactly one PDF/DOCX/TXT file, title field, an
 * opt-in AI enhancement checkbox (Stage 14 — same shared step as pasted
 * text, your own provider key, Settings-linked), client mirrors of server
 * validation (instant feedback only — the server rules), an honest pending
 * state, and server-error mapping by backend `code`.
 *
 * Progress honesty: `fetch` exposes no upload-progress events, so the form
 * shows ONE indeterminate state ("Uploading and analyzing…") with a caption
 * describing the pipeline — never a fake percentage.
 */

import { useId, useState } from "react";
import Link from "next/link";
import { FileText, Loader2, Upload, X } from "lucide-react";

import type { AnalysisResult } from "@/types/analysis";
import { UPLOAD_LIMITS, formatBytes, hasAllowedExtension, uploadDocument } from "@/lib/documents";
import { analysisErrorMessage } from "@/lib/analysis-errors";
import { cn } from "@/lib/utils";

import { FormAlert, TextField } from "../auth/fields";

export interface UploadDraft {
  title: string;
}

/** Instant client verdict (the server re-verifies everything authoritatively). */
function describeClientRejection(file: File): string | null {
  if (file.size === 0) return "That file is empty, so there is nothing to analyze.";
  if (!hasAllowedExtension(file.name)) {
    return "Choose a PDF, DOCX, or TXT file. Other formats are not supported.";
  }
  if (file.size > UPLOAD_LIMITS.maxBytes) {
    return `That file is ${formatBytes(file.size)} — uploads are limited to ${formatBytes(UPLOAD_LIMITS.maxBytes)}.`;
  }
  return null;
}

export function DocumentUploadForm({
  initial,
  onResult,
}: {
  /** Draft title to resume with (the file itself cannot persist). */
  initial?: UploadDraft;
  onResult: (result: AnalysisResult, draft: UploadDraft) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [aiEnhance, setAiEnhance] = useState(false);
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ file?: string; title?: string }>({});

  const inputId = useId();
  const fileErrorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const aiEnhanceId = useId();

  const titleTooLong = title.length > UPLOAD_LIMITS.maxTitle;
  // Length violations surface LIVE (derived, not submit-gated): the submit
  // button disables on them, so submit-only errors would strand users with a
  // dead button and no explanation. Server field errors take precedence.
  const liveTitleError = titleTooLong ? "Keep the title under 200 characters." : undefined;

  function selectFiles(files: FileList | File[] | null) {
    if (pending) return;
    const picked = files === null ? [] : Array.from(files);
    if (picked.length === 0) return;
    if (picked.length > 1) {
      setFile(null);
      setFieldErrors((previous) => ({ ...previous, file: "Drop one file at a time." }));
      return;
    }
    const [candidate] = picked;
    if (candidate === undefined) return; // unreachable: length is exactly 1 here
    const rejection = describeClientRejection(candidate);
    if (rejection !== null) {
      setFile(null);
      setFieldErrors((previous) => ({ ...previous, file: rejection }));
      return;
    }
    setFile(candidate);
    setFieldErrors((previous) => ({ ...previous, file: undefined }));
    setFormError(null);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    if (file === null) {
      setFormError(null);
      setFieldErrors((previous) => ({ ...previous, file: "Choose a file to begin." }));
      return;
    }
    if (titleTooLong) {
      setFormError(null);
      setFieldErrors({ title: "Keep the title under 200 characters." });
      return;
    }
    setPending(true);
    setFormError(null);
    setFieldErrors({});
    try {
      const { analysis } = await uploadDocument({ file, title, aiEnhance });
      onResult(analysis, { title });
    } catch (err: unknown) {
      // The server's verdict reads as form-level copy (the file row carries
      // client pre-checks only; field-mapping a file input helps nobody).
      setFormError(analysisErrorMessage(err));
    } finally {
      setPending(false);
    }
  }

  function handleRemove() {
    setFile(null);
    setFormError(null);
    setFieldErrors((previous) => ({ ...previous, file: undefined }));
  }

  const titleError = fieldErrors.title ?? liveTitleError;
  const fileError = fieldErrors.file;

  return (
    <form onSubmit={handleSubmit} aria-busy={pending} className="mt-8 space-y-6">
      <TextField
        label="Title (optional)"
        name="title"
        value={title}
        onChange={(value) => {
          setTitle(value);
          if (fieldErrors.title !== undefined) {
            setFieldErrors((previous) => ({ ...previous, title: undefined }));
          }
        }}
        error={titleError}
        hint="Blank titles save under the file's name."
        placeholder="e.g. Login SRS — v2"
        autoComplete="off"
        disabled={pending}
      />

      <div>
        <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[13px] font-medium text-ink-soft">SRS file</span>
          <p className="font-mono text-xs text-ink-faint">
            PDF · DOCX · TXT · up to {formatBytes(UPLOAD_LIMITS.maxBytes)}
          </p>
        </div>
        {file === null ? (
          <div
            onDragEnter={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              event.preventDefault();
              setDragging(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              selectFiles(event.dataTransfer.files);
            }}
            className={cn(
              "relative rounded-input border border-dashed bg-white shadow-sm transition outline-none focus-within:border-signal focus-within:ring-2 focus-within:ring-signal/25",
              dragging ? "border-signal bg-signal/5" : "border-line",
              fileError && "border-critic focus-within:border-critic focus-within:ring-critic/25",
              pending && "opacity-70",
            )}
          >
            <input
              id={inputId}
              type="file"
              accept={UPLOAD_LIMITS.extensions.join(",")}
              disabled={pending}
              onChange={(event) => {
                selectFiles(event.target.files);
                event.target.value = ""; // allow re-picking the same file
              }}
              aria-label="SRS file"
              aria-invalid={fileError ? true : undefined}
              aria-describedby={fileError ? `${fileErrorId} ${hintId}` : hintId}
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
            />
            <div
              aria-hidden
              className="pointer-events-none flex flex-col items-center px-6 py-10 text-center"
            >
              <Upload className="size-6 text-ink-faint" />
              <p className="mt-3 text-[15px] font-medium text-ink">
                Drag your file here, or <span className="underline">browse</span>
              </p>
              <p id={hintId} className="mt-1 text-[13px] leading-relaxed text-ink-faint">
                One PDF, DOCX, or TXT file · up to {formatBytes(UPLOAD_LIMITS.maxBytes)}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-input border border-line bg-white px-4 py-3 shadow-sm">
            <FileText className="size-5 shrink-0 text-signal" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-medium text-ink">{file.name}</p>
              <p className="font-mono text-xs text-ink-faint">{formatBytes(file.size)}</p>
            </div>
            <button
              type="button"
              onClick={handleRemove}
              disabled={pending}
              aria-label={`Remove ${file.name}`}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-50"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        )}
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-faint">
          Your file is validated, its text extracted, then the same analysis runs as for pasted
          text. Large files can take up to a minute.
        </p>
        {fileError ? (
          <p
            id={fileErrorId}
            className="mt-1.5 text-[13px] leading-relaxed font-medium text-critic"
          >
            {fileError}
          </p>
        ) : null}
      </div>

      <div className="flex items-start gap-3 rounded-card border border-line bg-paper p-4">
        <input
          id={aiEnhanceId}
          type="checkbox"
          checked={aiEnhance}
          onChange={(event) => setAiEnhance(event.target.checked)}
          disabled={pending}
          className="mt-1 size-4 shrink-0 accent-signal"
        />
        <div>
          <label htmlFor={aiEnhanceId} className="text-[15px] font-medium text-ink">
            Enhance with AI
          </label>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
            Adds an AI-written overview plus per-requirement rewrites, generated with your own
            provider key. Deterministic scores and issues are unaffected either way.{" "}
            <Link
              href="/settings"
              className="font-medium text-signal underline decoration-signal/40 underline-offset-2 transition hover:decoration-signal"
            >
              Manage providers in Settings
            </Link>
            .
          </p>
        </div>
      </div>

      {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={pending || file === null || titleTooLong}
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-signal px-6 py-2.5 text-[15px] font-semibold text-white shadow-sm transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
        >
          {pending ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden />
              {aiEnhance ? "Uploading and analyzing with AI…" : "Uploading and analyzing…"}
            </>
          ) : (
            "Upload and analyze"
          )}
        </button>
      </div>
    </form>
  );
}
