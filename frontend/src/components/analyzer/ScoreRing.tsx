"use client";

import { motion } from "motion/react";

import type { AnalysisBand } from "@/types/analysis";

/** Band vocabulary shared with history rows (color never stands alone — §10). */
export const BAND_LABELS: Record<AnalysisBand, string> = {
  low: "Low ambiguity",
  moderate: "Moderate ambiguity",
  high: "High ambiguity",
  very_high: "Very high ambiguity",
};

const BAND_STYLES: Record<AnalysisBand, string> = {
  low: "text-signal",
  moderate: "text-sev-medium",
  high: "text-sev-high",
  very_high: "text-sev-critical",
};

const RADIUS = 34;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Overall ambiguity score (0–100) as a restrained progress ring + band label.
 * The number is a heuristic indicator, not a measurement — the parent view
 * carries that disclaimer; this component just renders it honestly (with a
 * full text equivalent for assistive tech).
 */
export function ScoreRing({ score, band }: { score: number | null; band: AnalysisBand | null }) {
  if (score === null || band === null) {
    return (
      <div className="flex items-center gap-4">
        <p className="font-mono text-xs text-ink-faint">Not scored</p>
      </div>
    );
  }
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="flex items-center gap-4">
      <div
        role="img"
        aria-label={`Ambiguity score ${clamped} out of 100, ${BAND_LABELS[band].toLowerCase()}`}
        className={`relative size-24 shrink-0 ${BAND_STYLES[band]}`}
      >
        <svg viewBox="0 0 80 80" className="size-full -rotate-90" aria-hidden>
          <circle cx="40" cy="40" r={RADIUS} fill="none" strokeWidth="7" className="stroke-line" />
          <motion.circle
            cx="40"
            cy="40"
            r={RADIUS}
            fill="none"
            strokeWidth="7"
            strokeLinecap="round"
            stroke="currentColor"
            strokeDasharray={CIRCUMFERENCE}
            initial={{ strokeDashoffset: CIRCUMFERENCE }}
            animate={{ strokeDashoffset: CIRCUMFERENCE * (1 - clamped / 100) }}
            transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>
        <p aria-hidden className="absolute inset-0 flex items-baseline justify-center pt-7">
          <span className="text-2xl font-semibold tracking-tight text-ink tabular-nums">
            {clamped}
          </span>
          <span className="ml-0.5 font-mono text-[11px] text-ink-faint">/100</span>
        </p>
      </div>
      <div className="min-w-0">
        <p className="text-lg font-semibold tracking-[-0.01em]">{BAND_LABELS[band]}</p>
        <p className="mt-1 font-mono text-xs text-ink-faint">overall score</p>
      </div>
    </div>
  );
}
