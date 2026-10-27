"use client";

/**
 * Debounced value (Stage 10: history search calls the backend `q` endpoint,
 * so keystrokes must not fan out into requests — UI_UX/report-local filters
 * stay instant and never use this). Emits the latest value after `delayMs`
 * of quiet; unmounts and rapid changes cancel the pending emit.
 */

import { useEffect, useState } from "react";

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
