"use client";

/**
 * SRS text input + analysis submit (Stage 07: submit segments, detects, scores).
 * Large editor with live character/word counts, title field, an opt-in AI
 * enhancement checkbox (Stage 14 — your own provider key, Settings-linked),
 * client mirrors of server validation
 * (instant feedback only — the server rules), pending/disabled states, and
 * server-error mapping by backend `code`. Counts are plain string math, NOT
 * segmentation — no per-keystroke analysis happens here, ever.
 */

import { useId, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import type { AnalysisResult } from "@/types/analysis";
import { ANALYZER_LIMITS, createAnalysis } from "@/lib/analysis";
import { analysisErrorMessage, analysisFieldErrors } from "@/lib/analysis-errors";
import { cn } from "@/lib/utils";

import { FormAlert, TextField } from "../auth/fields";

export interface AnalyzerDraft {
  title: string;
  text: string;
}

function countWords(value: string): number {
  const trimmed = value.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

export function AnalyzerForm({
  initial,
  onResult,
}: {
  /** Draft to resume with (set when returning from a preview). */
  initial?: AnalyzerDraft;
  onResult: (result: AnalysisResult, draft: AnalyzerDraft) => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [text, setText] = useState(initial?.text ?? "");
  const [aiEnhance, setAiEnhance] = useState(false);
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ title?: string; text?: string }>({});

  const textareaId = useId();
  const textErrorId = `${textareaId}-error`;
  const countsId = `${textareaId}-counts`;
  const aiEnhanceId = useId();

  const charCount = text.length;
  const wordCount = countWords(text);
  const overLimit = charCount > ANALYZER_LIMITS.maxChars;
  const titleTooLong = title.length > ANALYZER_LIMITS.maxTitle;
  const hasContent = title !== "" || text !== "";
  // Length violations surface LIVE (derived, not submit-gated): the submit
  // button disables on them, so submit-only errors would strand users with a
  // dead button and no explanation. Server field errors take precedence.
  const liveTitleError = titleTooLong ? "Keep the title under 200 characters." : undefined;
  const liveTextError =
    overLimit && !pending ? "Keep your SRS under 200,000 characters." : undefined;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    if (text.trim() === "") {
      setFormError(null);
      setFieldErrors({ text: "Paste your SRS text to begin." });
      return;
    }
    if (overLimit) {
      setFormError(null);
      setFieldErrors({ text: "Keep your SRS under 200,000 characters." });
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
      const result = await createAnalysis({ title, text, aiEnhance });
      onResult(result, { title, text });
    } catch (err: unknown) {
      const fields = analysisFieldErrors(err);
      if (fields.text !== undefined || fields.title !== undefined) {
        setFieldErrors({ text: fields.text, title: fields.title });
      } else {
        setFormError(analysisErrorMessage(err));
      }
    } finally {
      setPending(false);
    }
  }

  function handleClear() {
    setTitle("");
    setText("");
    setFormError(null);
    setFieldErrors({});
  }

  const titleError = fieldErrors.title ?? liveTitleError;
  const textError = fieldErrors.text ?? liveTextError;

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
        hint="Blank titles save as “Untitled SRS Analysis”."
        placeholder="e.g. Login SRS — v2"
        autoComplete="off"
        disabled={pending}
      />

      <div>
        <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
          <label htmlFor={textareaId} className="text-[13px] font-medium text-ink-soft">
            SRS text
          </label>
          <p
            id={countsId}
            className={cn(
              "font-mono text-xs",
              overLimit ? "font-medium text-sev-critical" : "text-ink-faint",
            )}
          >
            {charCount.toLocaleString("en-US")} / {ANALYZER_LIMITS.maxChars.toLocaleString("en-US")}{" "}
            characters · {wordCount.toLocaleString("en-US")} words
          </p>
        </div>
        <textarea
          id={textareaId}
          name="text"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            if (fieldErrors.text !== undefined) {
              setFieldErrors((previous) => ({ ...previous, text: undefined }));
            }
          }}
          disabled={pending}
          rows={14}
          placeholder={
            "Paste your SRS here — for example:\n\nFR-001: The system shall allow login with email.\n\n1. The admin must approve new accounts.\n- The audit log shall record every login attempt."
          }
          aria-invalid={textError ? true : undefined}
          aria-describedby={textError ? `${textErrorId} ${countsId}` : countsId}
          className={cn(
            "min-h-80 w-full rounded-input border border-line bg-white px-3.5 py-2.5 text-[15px] leading-relaxed text-ink shadow-sm outline-none transition placeholder:text-ink-faint disabled:cursor-not-allowed disabled:bg-paper-deep disabled:opacity-70",
            textError
              ? "border-critic focus:border-critic focus:ring-2 focus:ring-critic/25"
              : "focus:border-signal focus:ring-2 focus:ring-signal/25",
          )}
        />
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-faint">
          Numbered, bulleted, or ID-tagged statements segment best; plain paragraphs need
          requirement language (shall / must / should).
        </p>
        {textError ? (
          <p
            id={textErrorId}
            className="mt-1.5 text-[13px] leading-relaxed font-medium text-critic"
          >
            {textError}
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
          disabled={pending || overLimit || titleTooLong}
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full bg-signal px-6 py-2.5 text-[15px] font-semibold text-white shadow-sm transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
        >
          {pending ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden />
              {aiEnhance ? "Analyzing requirements with AI…" : "Analyzing requirements…"}
            </>
          ) : (
            "Analyze requirements"
          )}
        </button>
        <button
          type="button"
          onClick={handleClear}
          disabled={pending || !hasContent}
          className="inline-flex items-center justify-center rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition hover:bg-paper-deep disabled:opacity-50"
        >
          Clear
        </button>
      </div>
    </form>
  );
}
