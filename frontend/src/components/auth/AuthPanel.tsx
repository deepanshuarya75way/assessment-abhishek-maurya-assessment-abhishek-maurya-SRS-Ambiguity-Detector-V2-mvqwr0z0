/**
 * Narrow card shell for the single-purpose auth pages (forgot / reset / verify)
 * + their Suspense fallback. Server components — no client JS.
 */

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export function AuthPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-md">
      <div className="rounded-2xl border border-line bg-white px-6 py-8 shadow-xl sm:px-8">
        {children}
      </div>
      <p className="mt-6 text-center">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-md text-[13px] font-medium text-ink-soft outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Back to home
        </Link>
      </p>
    </div>
  );
}

export function AuthPanelFallback({ label }: { label: string }) {
  return (
    <div aria-busy="true" aria-label={label} className="py-4">
      <div className="animate-pulse space-y-3">
        <div className="h-7 w-48 rounded-lg bg-paper-deep" />
        <div className="h-4 w-full rounded bg-paper-deep" />
        <div className="h-11 rounded-xl bg-paper-deep" />
      </div>
    </div>
  );
}
