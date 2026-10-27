"use client";

/**
 * History pager (Stage 10): previous/next over the backend page envelope.
 * Page count derives from the envelope `total`/`page_size` (exact, never
 * guessed); single-page results render no pager at all.
 */

export function HistoryPagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;
  const button =
    "inline-flex min-h-[44px] items-center justify-center rounded-full border border-line px-5 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent";
  return (
    <nav aria-label="History pages" className="mt-6 flex items-center justify-between gap-3">
      <button
        type="button"
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        className={button}
      >
        Previous
      </button>
      <p aria-current="page" className="font-mono text-xs text-ink-faint">
        Page {page} of {totalPages}
      </p>
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        className={button}
      >
        Next
      </button>
    </nav>
  );
}
