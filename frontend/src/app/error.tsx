"use client";

import { useEffect } from "react";

import { Container } from "@/components/layout/Container";
import { reportRouteError } from "@/lib/monitoring";

/**
 * Global error fallback (App Router `error.tsx` convention).
 * Catches render errors below the root layout; `reset()` retries the route.
 * Never renders error details — production users get a safe message only.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportRouteError(error);
  }, [error]);

  return (
    <Container className="flex min-h-dvh max-w-2xl flex-col items-start justify-center">
      <p className="font-mono text-xs tracking-[0.2em] text-sev-critical uppercase">Error</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">Something went wrong.</h1>
      <p className="mt-3 leading-relaxed text-ink-soft">
        This section failed to render. You can try again — no data has been lost.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-input bg-ink px-5 py-2.5 text-sm font-medium text-paper transition-transform duration-120 hover:-translate-y-px"
      >
        Try again
      </button>
    </Container>
  );
}
