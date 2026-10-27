import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Page-width container primitive — the single source of horizontal rhythm.
 * Centers content at the product max width with responsive gutters.
 * Override per page via `className` (e.g. a narrower `max-w-2xl`).
 */
export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-5xl px-6 sm:px-10", className)}>{children}</div>;
}
