"use client";

/**
 * Delete action for the saved-report route (Stage 09): explicit confirmation
 * dialog, never a one-click destroy. Focus moves to the safe default (Keep),
 * Tab cycles inside the dialog, Escape cancels, focus returns to the trigger
 * on close. A 404 at confirm time means "already gone" (other tab/device)
 * and resolves to the Analyzer like a success; anything else stays open with
 * the code-mapped error. Without `onDeleted` success leaves for the Analyzer
 * (report context — Stage 09); with it the caller stays and refreshes
 * (history rows — Stage 10).
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Trash } from "lucide-react";

import { analysisErrorMessage } from "@/lib/analysis-errors";
import { ApiRequestError } from "@/lib/api";
import { deleteAnalysis } from "@/lib/analysis";

export function DeleteAnalysisButton({
  analysisId,
  title,
  onDeleted,
  compact = false,
}: {
  analysisId: string;
  title: string;
  /** Stay-on-page success path (history): called after the dialog closes. */
  onDeleted?: () => void;
  /** Row-sized icon trigger with a title-named label (history table). */
  compact?: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (!open) {
      if (wasOpen.current) {
        wasOpen.current = false;
        triggerRef.current?.focus();
      }
      return;
    }
    wasOpen.current = true;
    cancelRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  function close() {
    if (!pending) setOpen(false);
  }

  /** Escape cancels; Tab cycles between the two dialog buttons. */
  function handleDialogKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const first = cancelRef.current;
    const last = confirmRef.current;
    if (first === null || last === null) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function handleConfirm() {
    setPending(true);
    setError(null);
    try {
      await deleteAnalysis(analysisId);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        // Already gone (deleted in another tab/device) — same destination.
      } else {
        setPending(false);
        setError(analysisErrorMessage(err));
        return;
      }
    }
    if (onDeleted === undefined) {
      router.push("/analyzer");
      return;
    }
    setPending(false);
    setOpen(false);
    onDeleted();
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={compact ? `Delete ${title}` : undefined}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
        className={
          compact
            ? "inline-flex size-11 items-center justify-center rounded-full border border-line text-ink-soft transition outline-none hover:border-critic/40 hover:text-critic focus-visible:ring-2 focus-visible:ring-critic/50"
            : "inline-flex items-center justify-center gap-2 rounded-full border border-critic/40 px-5 py-2.5 text-[15px] font-medium text-critic transition outline-none hover:bg-critic/10 focus-visible:ring-2 focus-visible:ring-critic/50"
        }
      >
        <Trash className="size-4" aria-hidden />
        {compact ? null : "Delete"}
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 [padding-bottom:max(1rem,env(safe-area-inset-bottom))] [padding-top:max(1rem,env(safe-area-inset-top))]">
          <div aria-hidden className="absolute inset-0 bg-ink/45" />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-analysis-title"
            aria-describedby="delete-analysis-description"
            onKeyDown={handleDialogKeyDown}
            className="relative max-h-[min(90vh,calc(100dvh-2rem))] w-full max-w-md overflow-y-auto overscroll-contain rounded-card border border-line bg-paper p-6 shadow-xl"
          >
            <h2 id="delete-analysis-title" className="text-lg font-semibold tracking-[-0.01em]">
              Delete this analysis?
            </h2>
            <p
              id="delete-analysis-description"
              className="mt-2 text-sm leading-relaxed text-ink-soft"
            >
              <span className="block truncate font-medium text-ink" title={title}>
                {title}
              </span>
              <span className="mt-1 block">
                This permanently deletes the analysis with its requirements and issues. This cannot
                be undone.
              </span>
            </p>
            {error !== null ? (
              <p role="alert" className="mt-3 text-sm font-medium text-critic">
                {error}
              </p>
            ) : null}
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                ref={cancelRef}
                type="button"
                onClick={close}
                disabled={pending}
                className="inline-flex items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
              >
                Keep analysis
              </button>
              <button
                ref={confirmRef}
                type="button"
                onClick={handleConfirm}
                disabled={pending}
                className="inline-flex min-h-[44px] items-center justify-center rounded-full bg-critic px-5 py-2 text-sm font-semibold text-white transition outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-critic/50 disabled:opacity-60"
              >
                {pending ? "Deleting…" : "Delete analysis"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
