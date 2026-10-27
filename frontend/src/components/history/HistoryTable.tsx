"use client";

/**
 * History rows (Stage 10): ONE semantic table that CSS-transforms into cards
 * on small screens (UI_UX_SPEC §11) — a single DOM, so no duplicated
 * interactive controls. Every value is the persisted summary, rendered
 * verbatim (scores, bands, counts are never recomputed). Title and Open both
 * lead to the Stage 09 report; delete reuses the explicit-confirm dialog.
 */

import Link from "next/link";
import { motion } from "motion/react";

import type { AnalysisBand, AnalysisSummary } from "@/types/analysis";
import { DeleteAnalysisButton } from "@/components/analyzer/DeleteAnalysisButton";
import { BAND_LABELS } from "@/components/analyzer/ScoreRing";

const BAND_DOT: Record<AnalysisBand, string> = {
  low: "bg-signal",
  moderate: "bg-sev-medium",
  high: "bg-sev-high",
  very_high: "bg-sev-critical",
};

function formatHistoryDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

function sourceLabel(item: AnalysisSummary): string {
  if (item.document !== null) {
    return `File ${item.document.filename} (${item.document.file_type.toUpperCase()})`;
  }
  return "Pasted SRS text";
}

function ScoreCell({ item }: { item: AnalysisSummary }) {
  if (item.status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-critic">
        <span aria-hidden className="size-1.5 rounded-full bg-current" />
        Failed
      </span>
    );
  }
  if (item.score === null || item.band === null) {
    return <span className="text-sm text-ink-faint">Not scored</span>;
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span aria-hidden className={`size-1.5 rounded-full ${BAND_DOT[item.band]}`} />
      <span className="font-semibold tabular-nums">{item.score}</span>
      <span className="text-ink-soft">· {BAND_LABELS[item.band]}</span>
    </span>
  );
}

export function HistoryTable({
  items,
  stale,
  onDeleted,
}: {
  items: AnalysisSummary[];
  /** A newer page is loading: dim + expose busy (never present stale as current). */
  stale: boolean;
  /** Refetch the current page after a row delete (parent owns paging). */
  onDeleted: () => void;
}) {
  return (
    <div
      aria-busy={stale}
      className={stale ? "pointer-events-none opacity-60 transition-opacity" : "transition-opacity"}
    >
      <table className="block w-full sm:table">
        <caption className="sr-only">
          Your analyses, newest first. Each row opens its saved report or deletes it.
        </caption>
        <thead className="hidden sm:table-header-group">
          <tr className="border-b border-line text-left font-mono text-[11px] tracking-[0.12em] text-ink-faint uppercase">
            <th scope="col" className="px-3 py-2 font-medium">
              Analysis
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Score
            </th>
            <th scope="col" className="px-3 py-2 font-medium tabular-nums">
              Requirements
            </th>
            <th scope="col" className="px-3 py-2 font-medium tabular-nums">
              Issues
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              <span className="sr-only">Row actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="block space-y-3 sm:table-row-group sm:space-y-0">
          {items.map((item, index) => (
            <motion.tr
              key={item.id}
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true, margin: "-20px" }}
              transition={{ duration: 0.4, delay: Math.min(index * 0.04, 0.24) }}
              className="block rounded-card border border-line bg-paper p-4 sm:table-row sm:rounded-none sm:border-0 sm:border-b sm:border-line sm:bg-transparent sm:p-0"
            >
              <td className="block px-0 py-0 sm:table-cell sm:px-3 sm:py-3.5">
                <Link
                  href={`/analysis/${item.id}`}
                  title={item.title}
                  className="block min-w-0 text-[15px] font-semibold [overflow-wrap:anywhere] text-ink underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-signal/50 sm:truncate sm:[overflow-wrap:normal]"
                >
                  {item.title}
                </Link>
                <p
                  className="mt-1 font-mono text-xs [overflow-wrap:anywhere] text-ink-soft sm:truncate sm:[overflow-wrap:normal]"
                  title={sourceLabel(item)}
                >
                  {sourceLabel(item)}
                </p>
                <p className="mt-0.5 font-mono text-xs text-ink-faint">
                  {formatHistoryDate(item.created_at)}
                </p>
              </td>
              <td
                data-label="Score"
                className="mt-3 block px-0 py-0 before:mr-2 before:font-mono before:text-[11px] before:tracking-[0.12em] before:text-ink-faint before:uppercase before:content-[attr(data-label)] sm:mt-0 sm:table-cell sm:px-3 sm:py-3.5 sm:before:content-none"
              >
                <ScoreCell item={item} />
              </td>
              <td
                data-label="Requirements"
                className="mt-1.5 block px-0 py-0 text-sm tabular-nums before:mr-2 before:font-mono before:text-[11px] before:tracking-[0.12em] before:text-ink-faint before:uppercase before:content-[attr(data-label)] sm:mt-0 sm:table-cell sm:px-3 sm:py-3.5 sm:before:content-none"
              >
                {item.requirements_count}
              </td>
              <td
                data-label="Issues"
                className="mt-1.5 block px-0 py-0 text-sm tabular-nums before:mr-2 before:font-mono before:text-[11px] before:tracking-[0.12em] before:text-ink-faint before:uppercase before:content-[attr(data-label)] sm:mt-0 sm:table-cell sm:px-3 sm:py-3.5 sm:before:content-none"
              >
                {item.issues_count}
              </td>
              <td className="mt-3 block px-0 py-0 sm:mt-0 sm:table-cell sm:px-3 sm:py-3.5 sm:text-right">
                <span className="flex items-center gap-2 sm:justify-end">
                  <Link
                    href={`/analysis/${item.id}`}
                    aria-label={`Open ${item.title}`}
                    className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-line px-5 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
                  >
                    Open
                  </Link>
                  <DeleteAnalysisButton
                    analysisId={item.id}
                    title={item.title}
                    compact
                    onDeleted={onDeleted}
                  />
                </span>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
