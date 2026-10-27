"use client";

/**
 * Subtle copy-to-clipboard action (Stage 09: requirement text, suggestions).
 * Copies ONLY the given text (never hidden metadata); confirms via an
 * inline label swap announced politely — no intrusive notifications. Failure
 * (denied clipboard permission, insecure context) reads as honest inline
 * copy, never a silent no-op.
 */

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

export function CopyButton({
  text,
  label,
  className,
}: {
  /** Exact text placed on the clipboard. */
  text: string;
  /** Visible action label (e.g. "Copy", "Copy suggestion"). */
  label: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  async function handleCopy() {
    setFailed(false);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setFailed(true);
      return;
    }
    setCopied(true);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? `${label} — copied` : label}
      className={cn(
        "inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-mono text-xs font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50",
        copied && "border-signal/40 text-signal",
        className,
      )}
    >
      <span aria-hidden className="inline-flex">
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </span>
      <span aria-live="polite">{failed ? "Copy failed" : copied ? "Copied" : label}</span>
    </button>
  );
}
