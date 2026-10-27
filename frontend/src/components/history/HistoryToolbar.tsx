"use client";

/**
 * History search + filters + sort (Stage 10). All three hit the backend list
 * API directly (server search `q`, `band`/`source_type` filters, the four
 * contract sorts) — the toolbar owns no data, only the request parameters.
 * The count line is the polite announcer for every result change.
 */

import { Search } from "lucide-react";

import type { AnalysisBand, AnalysisSort } from "@/types/analysis";

const BAND_OPTIONS: { value: AnalysisBand | "all"; label: string }[] = [
  { value: "all", label: "All bands" },
  { value: "low", label: "Low" },
  { value: "moderate", label: "Moderate" },
  { value: "high", label: "High" },
  { value: "very_high", label: "Very high" },
];

const SOURCE_OPTIONS: { value: "all" | "text" | "document"; label: string }[] = [
  { value: "all", label: "All sources" },
  { value: "text", label: "Pasted text" },
  { value: "document", label: "Uploaded files" },
];

const SORT_OPTIONS: { value: AnalysisSort; label: string }[] = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "-score", label: "Highest score" },
  { value: "score", label: "Lowest score" },
];

const LABEL = "font-mono text-[11px] tracking-[0.12em] text-ink-faint uppercase";
const SELECT =
  "mt-1.5 w-full rounded-lg border border-line bg-white px-2.5 py-2 text-sm text-ink outline-none transition focus-visible:ring-2 focus-visible:ring-signal/50";

export function HistoryToolbar({
  query,
  onQueryChange,
  band,
  onBandChange,
  sourceType,
  onSourceTypeChange,
  sort,
  onSortChange,
  shown,
  total,
  searching,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  band: AnalysisBand | "all";
  onBandChange: (value: AnalysisBand | "all") => void;
  sourceType: "all" | "text" | "document";
  onSourceTypeChange: (value: "all" | "text" | "document") => void;
  sort: AnalysisSort;
  onSortChange: (value: AnalysisSort) => void;
  /** Rows on this page (from the envelope, never guessed). */
  shown: number;
  /** Envelope total for the current search/filter set. */
  total: number;
  /** Keystrokes not yet sent (debounce pending) — say so, don't fake results. */
  searching: boolean;
}) {
  return (
    <div className="rounded-card border border-line bg-paper p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
        <div className="min-w-0 flex-1">
          <label htmlFor="history-search" className={LABEL}>
            Search
          </label>
          <div className="relative mt-1.5">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint"
            />
            <input
              id="history-search"
              type="search"
              value={query}
              maxLength={200}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search titles and filenames…"
              className="w-full rounded-lg border border-line bg-white py-2 pr-3 pl-9 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:ring-2 focus-visible:ring-signal/50"
            />
          </div>
          <p className="mt-1.5 font-mono text-[11px] text-ink-faint">
            Searches your full history — titles and uploaded filenames.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:w-auto">
          <div>
            <label htmlFor="history-filter-band" className={LABEL}>
              Band
            </label>
            <select
              id="history-filter-band"
              value={band}
              onChange={(event) => onBandChange(event.target.value as AnalysisBand | "all")}
              className={SELECT}
            >
              {BAND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="history-filter-source" className={LABEL}>
              Source
            </label>
            <select
              id="history-filter-source"
              value={sourceType}
              onChange={(event) =>
                onSourceTypeChange(event.target.value as "all" | "text" | "document")
              }
              className={SELECT}
            >
              {SOURCE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="history-sort" className={LABEL}>
              Sort
            </label>
            <select
              id="history-sort"
              value={sort}
              onChange={(event) => onSortChange(event.target.value as AnalysisSort)}
              className={SELECT}
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
      <p
        aria-live="polite"
        aria-atomic="true"
        className="mt-3 border-t border-line pt-3 font-mono text-xs text-ink-faint"
      >
        {searching
          ? "Searching…"
          : `Showing ${shown} of ${total} ${total === 1 ? "analysis" : "analyses"}`}
      </p>
    </div>
  );
}
