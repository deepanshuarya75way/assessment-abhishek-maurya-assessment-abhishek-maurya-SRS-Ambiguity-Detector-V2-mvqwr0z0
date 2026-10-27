"use client";

/**
 * Analysis history (`/history`, Stage 10): verified-users-only paged list of
 * owned analyses over the ready `GET /analysis` API (server search `q` +
 * `band`/`source_type` filters + the four contract sorts). Presentation-only:
 * scores, bands, and counts render verbatim from the envelope — nothing is
 * recalculated. Stale pages dim with `aria-busy` (never presented as
 * current); every filter/sort/search change resets to page 1; deletes
 * refetch with page-clamping. State stays local (the report toolbar
 * precedent — no query-param convention exists yet).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Inbox, TriangleAlert } from "lucide-react";

import type { AnalysisBand, AnalysisSort, AnalysisSummary } from "@/types/analysis";
import { Container } from "@/components/layout/Container";
import { Reveal } from "@/components/Reveal";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { analysisErrorMessage } from "@/lib/analysis-errors";
import { listAnalyses } from "@/lib/analysis";
import type { Collection } from "@/lib/api";
import { isSessionGone } from "@/lib/auth";

import { HistoryPagination } from "./HistoryPagination";
import { HistoryTable } from "./HistoryTable";
import { HistoryToolbar } from "./HistoryToolbar";

const SEARCH_DEBOUNCE_MS = 350;
/** Wrong-shape JSON has no backend code — mirrors lib/api's bad_response copy. */
const UNEXPECTED_RESPONSE = "The service returned an unexpected response.";

function isHistoryPage(value: unknown): value is Collection<AnalysisSummary> {
  if (typeof value !== "object" || value === null) return false;
  const { items, page, page_size, total } = value as Record<string, unknown>;
  return (
    Array.isArray(items) &&
    typeof page === "number" &&
    Number.isInteger(page) &&
    typeof page_size === "number" &&
    Number.isInteger(page_size) &&
    typeof total === "number" &&
    Number.isInteger(total)
  );
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: Collection<AnalysisSummary>; key: string }
  | { status: "session-gone" }
  | { status: "load-failed"; message: string };

function BackLink() {
  return (
    <Link
      href="/analyzer"
      className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
    >
      <ArrowLeft className="size-3.5" aria-hidden />
      Analyzer
    </Link>
  );
}

function HistoryContent() {
  const [query, setQuery] = useState("");
  const [band, setBand] = useState<AnalysisBand | "all">("all");
  const [sourceType, setSourceType] = useState<"all" | "text" | "document">("all");
  const [sort, setSort] = useState<AnalysisSort>("-created_at");
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const debouncedQuery = useDebouncedValue(query, SEARCH_DEBOUNCE_MS);

  const trimmed = debouncedQuery.trim();
  const key = JSON.stringify([trimmed, band, sourceType, sort, page, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    const requestKey = JSON.stringify([
      debouncedQuery.trim(),
      band,
      sourceType,
      sort,
      page,
      refreshKey,
    ]);
    listAnalyses({
      page,
      sort,
      ...(band === "all" ? {} : { band }),
      ...(sourceType === "all" ? {} : { source_type: sourceType }),
      ...(debouncedQuery.trim() === "" ? {} : { q: debouncedQuery.trim() }),
    }).then(
      (data) => {
        if (cancelled) return;
        if (!isHistoryPage(data)) {
          setState({ status: "load-failed", message: UNEXPECTED_RESPONSE });
          return;
        }
        if (data.items.length === 0 && page > 1) {
          // Page emptied (delete, or concurrent change elsewhere) — step back.
          setPage(page - 1);
          return;
        }
        setState({ status: "ready", data, key: requestKey });
      },
      (err: unknown) => {
        if (cancelled) return;
        if (isSessionGone(err)) setState({ status: "session-gone" });
        else setState({ status: "load-failed", message: analysisErrorMessage(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, band, sourceType, sort, page, refreshKey]);

  function handleQueryChange(value: string) {
    setQuery(value);
    setPage(1);
  }

  function handleBandChange(value: AnalysisBand | "all") {
    setBand(value);
    setPage(1);
  }

  function handleSourceTypeChange(value: "all" | "text" | "document") {
    setSourceType(value);
    setPage(1);
  }

  function handleSortChange(value: AnalysisSort) {
    setSort(value);
    setPage(1);
  }

  function clearSearchAndFilters() {
    setQuery("");
    setBand("all");
    setSourceType("all");
    setPage(1);
  }

  const pristine = trimmed === "" && band === "all" && sourceType === "all";
  const stale = state.status === "ready" && state.key !== key;

  return (
    <Container className="py-10 sm:py-14">
      <BackLink />
      <Reveal>
        <p className="mt-4 font-mono text-xs tracking-[0.2em] text-signal uppercase">History</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.02em] text-balance sm:text-4xl">
          Analysis history
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-soft">
          Every analysis you have run, newest first. Search your titles and filenames, filter by
          score band or source, and open any row for its full saved report.
        </p>
      </Reveal>

      {state.status === "loading" ? (
        <div
          aria-busy="true"
          aria-label="Loading history"
          className="mt-8 rounded-card border border-line bg-paper p-8"
        >
          <div className="animate-pulse space-y-3">
            <div className="h-6 w-48 rounded-lg bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-2/3 rounded bg-paper-deep" />
          </div>
        </div>
      ) : null}

      {state.status === "session-gone" ? (
        <div role="status" className="mt-8 max-w-xl">
          <h2 className="text-2xl font-semibold tracking-[-0.02em]">Session expired</h2>
          <p className="mt-3 text-base leading-relaxed text-ink-soft">
            Sign in again to view your history.
          </p>
          <p className="mt-5">
            <Link
              href="/login"
              className="inline-flex items-center justify-center rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Sign in
            </Link>
          </p>
        </div>
      ) : null}

      {state.status === "load-failed" ? (
        <div
          role="alert"
          className="mt-8 flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
        >
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-gold" aria-hidden />
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.01em]">
              Couldn&apos;t load your history
            </h2>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">{state.message}</p>
            <button
              type="button"
              onClick={() => {
                setState({ status: "loading" });
                setRefreshKey((count) => count + 1);
              }}
              className="mt-4 inline-flex items-center justify-center rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Retry
            </button>
          </div>
        </div>
      ) : null}

      {state.status === "ready" ? (
        <div className="mt-8">
          {pristine && state.data.total === 0 ? null : (
            <HistoryToolbar
              query={query}
              onQueryChange={handleQueryChange}
              band={band}
              onBandChange={handleBandChange}
              sourceType={sourceType}
              onSourceTypeChange={handleSourceTypeChange}
              sort={sort}
              onSortChange={handleSortChange}
              shown={state.data.items.length}
              total={state.data.total}
              searching={query.trim() !== trimmed}
            />
          )}
          {state.data.total === 0 && pristine ? (
            <div
              role="status"
              className="flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
            >
              <Inbox className="mt-0.5 size-5 shrink-0 text-ink-faint" aria-hidden />
              <div>
                <h2 className="text-lg font-semibold tracking-[-0.01em]">No analyses yet</h2>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
                  Run your first analysis and it will appear here with its score and summary.
                </p>
                <p className="mt-4">
                  <Link
                    href="/analyzer"
                    className="inline-flex items-center justify-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
                  >
                    Analyze requirements
                    <ArrowRight className="size-4" aria-hidden />
                  </Link>
                </p>
              </div>
            </div>
          ) : null}
          {state.data.total === 0 && !pristine ? (
            <div
              role="status"
              className="mt-6 rounded-card border border-dashed border-line bg-paper p-6 text-center"
            >
              <h2 className="text-[15px] font-semibold">No matching results</h2>
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                Nothing in your history matches this search and filter set.
              </p>
              <button
                type="button"
                onClick={clearSearchAndFilters}
                className="mt-4 inline-flex items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
              >
                Clear search and filters
              </button>
            </div>
          ) : null}
          {state.data.items.length > 0 ? (
            <div className="mt-6">
              <HistoryTable
                items={state.data.items}
                stale={stale}
                onDeleted={() => setRefreshKey((count) => count + 1)}
              />
              <HistoryPagination
                page={state.data.page}
                pageSize={state.data.page_size}
                total={state.data.total}
                onPage={setPage}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </Container>
  );
}

export function HistoryScreen() {
  return (
    <ProtectedRoute>
      <HistoryContent />
    </ProtectedRoute>
  );
}
