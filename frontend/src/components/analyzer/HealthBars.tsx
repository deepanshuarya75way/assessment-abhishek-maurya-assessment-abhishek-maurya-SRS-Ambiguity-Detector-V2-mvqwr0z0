"use client";

/**
 * Supplementary health dimensions (Stage 09 report section, per UI_UX_SPEC
 * §7: slim bars that never compete with the score gauge). Values are the
 * persisted backend dimensions — each starts at 100 and subtracts only its
 * own detectors' deductions (the partition is documented in API_CONTRACT
 * §4.3). Bars are aria-hidden; every value is real text.
 */

import { useId } from "react";

import type { HealthDimensions } from "@/types/analysis";

const DIMENSIONS: { key: keyof HealthDimensions; label: string }[] = [
  { key: "clarity", label: "Clarity" },
  { key: "specificity", label: "Specificity" },
  { key: "measurability", label: "Measurability" },
  { key: "completeness", label: "Completeness" },
];

export function HealthBars({ health }: { health: HealthDimensions }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <h3
        id={headingId}
        className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
      >
        Requirement health
      </h3>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
        Same deductions, partitioned by dimension — not separate measurements.
      </p>
      <ul className="mt-3 space-y-2.5">
        {DIMENSIONS.map(({ key, label }) => (
          <li key={key}>
            <p className="flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium text-ink">{label}</span>
              <span className="shrink-0 font-mono text-[13px] text-ink-soft tabular-nums">
                {health[key]}
                <span className="text-ink-faint"> / 100</span>
              </span>
            </p>
            <span
              aria-hidden
              className="mt-1 block h-1.5 overflow-hidden rounded-full bg-paper-deep"
            >
              <span
                className="block h-full rounded-full bg-signal/70"
                style={{ width: `${Math.max(0, Math.min(100, health[key]))}%` }}
              />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
