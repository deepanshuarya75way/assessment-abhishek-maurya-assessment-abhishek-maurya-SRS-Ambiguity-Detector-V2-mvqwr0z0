"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { ApiRequestError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface LiveResponse {
  status: "ok";
  service: string;
  version: string;
}

type State =
  | { kind: "loading" }
  | { kind: "online"; version: string; latencyMs: number }
  | { kind: "offline"; message: string };

/**
 * Live API reachability card. Polls GET /health/live once on mount — proves the
 * contract envelope, CORS, and cookie wiring end to end (API_CONTRACT.md §4.1).
 */
export function ApiStatus({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    const started = performance.now();
    api<LiveResponse>("/health/live")
      .then((res) => {
        if (cancelled) return;
        setState({
          kind: "online",
          version: res.version,
          latencyMs: Math.round(performance.now() - started),
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiRequestError ? err.message : "Could not reach the analysis service.";
        setState({ kind: "offline", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
      className={cn("rounded-card border border-line bg-paper p-5", className)}
      role="status"
      aria-live="polite"
    >
      <p className="font-mono text-xs tracking-widest text-ink-faint uppercase">Backend API</p>
      <div className="mt-3 flex items-center gap-2.5">
        {state.kind === "loading" && (
          <>
            <Loader2 className="size-5 animate-spin text-ink-faint" aria-hidden />
            <span className="text-sm text-ink-soft">Contacting service…</span>
          </>
        )}
        {state.kind === "online" && (
          <>
            <CheckCircle2 className="size-5 text-signal" aria-hidden />
            <span className="text-sm font-medium">
              Online{" "}
              <span className="font-mono text-xs text-ink-faint">
                v{state.version} · {state.latencyMs} ms
              </span>
            </span>
          </>
        )}
        {state.kind === "offline" && (
          <>
            <AlertTriangle className="size-5 text-sev-high" aria-hidden />
            <span className="text-sm font-medium">{state.message}</span>
          </>
        )}
      </div>
    </motion.div>
  );
}
