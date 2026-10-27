"use client";

import type { ReactNode } from "react";
import { useId, useState } from "react";

import { motion } from "motion/react";
import { ChevronDown } from "lucide-react";

import type { AnalysisIssue, SegmentedRequirement, SegmentationStrategy } from "@/types/analysis";
import { requirementHealth } from "@/lib/reporting";
import { cn } from "@/lib/utils";

import { CopyButton } from "./CopyButton";
import { IssueCard } from "./IssueCard";
import { SeverityBadge } from "./SeverityBadge";

const STRATEGY_LABELS: Record<SegmentationStrategy, string> = {
  requirement_id: "ID-tagged",
  decimal: "Decimal",
  numbered: "Numbered",
  bullet: "Bullet",
  paragraph: "Paragraph",
};

interface Span {
  start: number;
  end: number;
}

/** Merge overlapping/clamping spans so highlights never nest or overrun. */
function unionSpans(textLength: number, issues: AnalysisIssue[]): Span[] {
  const clamped = issues
    .map((issue) => ({
      start: Math.max(0, Math.min(textLength, issue.start_offset)),
      end: Math.max(0, Math.min(textLength, issue.end_offset)),
    }))
    .filter((span) => span.start < span.end)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: Span[] = [];
  for (const span of clamped) {
    const last = merged[merged.length - 1];
    if (last && span.start <= last.end) {
      last.end = Math.max(last.end, span.end);
    } else {
      merged.push({ ...span });
    }
  }
  return merged;
}

/** Requirement text with detected phrases marked (React-escaped throughout). */
function MarkedText({ text, issues }: { text: string; issues: AnalysisIssue[] }) {
  if (issues.length === 0) {
    return <>{text}</>;
  }
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const span of unionSpans(text.length, issues)) {
    if (span.start > cursor) {
      nodes.push(text.slice(cursor, span.start));
    }
    nodes.push(
      <mark
        key={`${span.start}-${span.end}`}
        className="rounded-[3px] bg-gold-mist px-0.5 text-inherit"
      >
        {text.slice(span.start, span.end)}
      </mark>,
    );
    cursor = span.end;
  }
  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return <>{nodes}</>;
}

/**
 * One scored requirement: score + worst severity + highlighted text +
 * collapsible issues + optional suggested rewrite (Stage 14 — AI-labeled,
 * additive-only: the original text above is never modified; Stage 15 adds
 * the copy action + review-before-applying microcopy) +
 * segmentation provenance. The text stays visible; issues start collapsed
 * behind a toggle so long reports stay scannable (UI_UX_SPEC §30).
 * Parent-owned `expanded`/`onToggle` enable Expand-all; standalone usage
 * stays uncontrolled. Clean requirements say so instead of rendering an
 * empty issues block.
 */
export function RequirementCard({
  requirement,
  index = 0,
  expanded,
  onToggle,
}: {
  requirement: SegmentedRequirement;
  /** Position in the list — drives the capped stagger delay. */
  index?: number;
  /** Controlled open state (parent-owned for Expand-all). Omit for uncontrolled. */
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const count = requirement.issues.length;
  const [uncontrolled, setUncontrolled] = useState(false);
  const regionId = useId();
  const isOpen = expanded ?? uncontrolled;
  const health = requirementHealth(requirement);

  function toggle() {
    onToggle?.();
    if (expanded === undefined) setUncontrolled((open) => !open);
  }
  return (
    <motion.li
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.56, delay: Math.min(index * 0.05, 0.4), ease: [0.16, 1, 0.3, 1] }}
      className="rounded-card border border-line bg-paper p-5"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="rounded-md border border-line px-2 py-0.5 font-mono text-xs font-medium text-ink-soft">
          R-{requirement.position + 1}
        </span>
        {requirement.identifier ? (
          <span
            className="font-mono text-xs font-medium [overflow-wrap:anywhere] text-ink"
            title={requirement.identifier}
          >
            {requirement.identifier}
          </span>
        ) : null}
        {requirement.section ? (
          <span
            className="min-w-0 flex-1 basis-40 text-[13px] [overflow-wrap:anywhere] text-ink-faint sm:truncate sm:[overflow-wrap:normal]"
            title={requirement.section}
          >
            § {requirement.section}
          </span>
        ) : null}
        <span className="ml-auto inline-flex items-center gap-3">
          <span className="font-mono text-xs text-ink-faint">
            score{" "}
            <span className="text-sm font-semibold text-ink tabular-nums">
              {requirement.score ?? "—"}
            </span>
          </span>
          {requirement.severity ? <SeverityBadge severity={requirement.severity} /> : null}
        </span>
      </div>

      <div className="mt-3 flex flex-col items-start gap-3 min-[420px]:flex-row min-[420px]:justify-between">
        <p className="min-w-0 flex-1 text-[15px] leading-[1.65] [overflow-wrap:anywhere] whitespace-pre-wrap break-words">
          <MarkedText text={requirement.text} issues={requirement.issues} />
        </p>
        <CopyButton text={requirement.text} label="Copy" className="min-[420px]:mt-0.5" />
      </div>

      {count === 0 ? (
        <p className="mt-3 font-mono text-xs text-signal">No issues — reads clearly.</p>
      ) : (
        <div className="mt-3 border-t border-line pt-1">
          <button
            type="button"
            onClick={toggle}
            aria-expanded={isOpen}
            aria-controls={regionId}
            className="flex w-full items-center justify-between gap-2 rounded-md py-1.5 text-left font-mono text-xs text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
          >
            <span>
              {count === 1 ? "1 issue" : `${count} issues`} · {health.label}
            </span>
            <ChevronDown
              aria-hidden
              className={cn("size-4 shrink-0 transition-transform", isOpen && "rotate-180")}
            />
          </button>
          {isOpen ? (
            <div
              id={regionId}
              role="region"
              aria-label={`Detected issues for requirement ${requirement.position + 1}`}
            >
              <div className="mt-1">
                {requirement.issues.map((issue) => (
                  <IssueCard key={issue.id} issue={issue} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {requirement.suggested_rewrite ? (
        <div className="mt-3 rounded-lg border border-dashed border-line bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-mono text-[11px] tracking-[0.12em] text-ink-faint uppercase">
              {requirement.suggestion_source === "ai"
                ? "AI-suggested rewrite"
                : "Suggested rewrite"}
            </p>
            <CopyButton text={requirement.suggested_rewrite} label="Copy suggestion" />
          </div>
          <p className="mt-1.5 text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-wrap break-words text-ink-soft">
            {requirement.suggested_rewrite}
          </p>
          {requirement.suggestion_source === "ai" ? (
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-faint">
              AI-generated suggestion — review before applying. The original above is unchanged.
            </p>
          ) : null}
        </div>
      ) : null}

      <p className="mt-3 font-mono text-xs text-ink-faint">
        {`${STRATEGY_LABELS[requirement.segmentation.strategy]} · ${requirement.segmentation.confidence.toFixed(2)} · L${requirement.segmentation.line_start}–${requirement.segmentation.line_end}`}
      </p>
    </motion.li>
  );
}
