import { Loader2 } from "lucide-react";

/**
 * Global loading fallback (App Router `loading.tsx` convention).
 * Rendered during route transitions; feature routes may add their own
 * closer-to-the-data loading states later.
 */
export default function Loading() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <p className="flex items-center gap-2 font-mono text-sm text-ink-faint">
        <Loader2 className="size-4 animate-spin" aria-hidden /> Loading…
      </p>
    </div>
  );
}
