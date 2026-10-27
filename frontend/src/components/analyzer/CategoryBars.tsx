"use client";

/**
 * Issue-category summary as horizontal bars per UI_UX_SPEC §7 — readable
 * labels beat pie slices; a single restrained color (never rainbow
 * categories). The list itself is the accessible alternative (counts are
 * real text; bars are aria-hidden decoration). Serves the Stage 09 report
 * (default caption) AND the Stage 11 dashboard (account-wide caption).
 */

import { useId } from "react";

import type { CategoryCount } from "@/lib/reporting";

export function CategoryBars({
  counts,
  caption = "Counts within this analysis only — not account-wide trends.",
  headingLevel = "h3",
}: {
  counts: CategoryCount[];
  caption?: string;
  /** The dashboard nests this one level higher (clean h1 → h2 outline). */
  headingLevel?: "h2" | "h3";
}) {
  const headingId = useId();
  if (counts.length === 0) return null;
  const max = Math.max(...counts.map((entry) => entry.count));
  const Heading = headingLevel === "h2" ? "h2" : "h3";
  return (
    <section aria-labelledby={headingId}>
      <Heading
        id={headingId}
        className="font-mono text-[11px] tracking-[0.14em] text-ink-faint uppercase"
      >
        Issue categories
      </Heading>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">{caption}</p>
      <ul className="mt-3 space-y-2.5">
        {counts.map(({ category, count }) => (
          <li key={category}>
            <p className="flex items-baseline justify-between gap-3 text-sm">
              <span
                className="min-w-0 font-medium [overflow-wrap:anywhere] text-ink sm:truncate sm:[overflow-wrap:normal]"
                title={category}
              >
                {category}
              </span>
              <span className="shrink-0 font-mono text-[13px] text-ink-soft tabular-nums">
                {count}
              </span>
            </p>
            <span
              aria-hidden
              className="mt-1 block h-1.5 overflow-hidden rounded-full bg-paper-deep"
            >
              <span
                className="block h-full rounded-full bg-signal/70"
                style={{ width: `${(count / max) * 100}%` }}
              />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
