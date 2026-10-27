"use client";

import { useId, useState } from "react";

import { motion } from "motion/react";
import { ChevronDown } from "lucide-react";

import type { AnalysisIssue } from "@/types/analysis";

import { CopyButton } from "./CopyButton";
import { SeverityBadge } from "./SeverityBadge";

/**
 * One finding: category + severity + detected phrase, expanding to the
 * "Why was this flagged?" explanation (detector id, reason, suggestion).
 * Keyboard-operable button + region; animation is a quiet fade, not layout.
 */
export function IssueCard({ issue }: { issue: AnalysisIssue }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div className="border-t border-line py-3 first:border-t-0 first:pt-1 last:pb-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((was) => !was)}
        className="flex min-h-[44px] w-full items-center gap-3 rounded-md py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-signal/50"
      >
        <SeverityBadge severity={issue.severity} />
        <span
          className="min-w-0 flex-1 text-sm font-medium [overflow-wrap:anywhere] sm:truncate sm:[overflow-wrap:normal]"
          title={`${issue.category}: ${issue.phrase}`}
        >
          {issue.category}
          <span className="ml-2 font-mono text-[13px] font-normal text-ink-faint">
            “{issue.phrase}”
          </span>
        </span>
        <ChevronDown
          aria-hidden
          className={`size-4 shrink-0 text-ink-faint transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open ? (
        <motion.div
          id={panelId}
          role="region"
          aria-label={`Why this was flagged: ${issue.category}`}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
          className="pt-2 pl-1"
        >
          <p className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase">
            Why was this flagged?
          </p>
          {/* React-escaped by construction — reason/recommendation are backend
              templates, but the phrase interpolates matched source text. */}
          <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{issue.reason}</p>
          <p className="mt-2 font-mono text-xs text-ink-faint">rule · {issue.detector_id}</p>
          <p className="mt-3 font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase">
            Suggested fix
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{issue.recommendation}</p>
          <CopyButton text={issue.recommendation} label="Copy suggestion" className="mt-3" />
        </motion.div>
      ) : null}
    </div>
  );
}
