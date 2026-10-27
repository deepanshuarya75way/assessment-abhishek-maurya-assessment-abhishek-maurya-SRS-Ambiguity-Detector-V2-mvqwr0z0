"use client";

/**
 * Saved-report route screen (`/analysis/[id]`, Stage 09): authenticated-users-only.
 * foreign id reads back 404 without leaking anything). Ownership + existence
 * failures share one honest not-found panel (never "access denied", which
 * would confirm a foreign id exists); an exhausted session gets a sign-in
 * nudge; transient failures get a retry. The report itself is the same
 * `AnalysisResultView` the workspace shows — only the footer actions differ.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import type { AnalysisResult } from "@/types/analysis";
import { Container } from "@/components/layout/Container";
import { ApiRequestError } from "@/lib/api";
import { getAnalysis } from "@/lib/analysis";
import { isSessionGone } from "@/lib/auth";

import { ProtectedRoute } from "../auth/ProtectedRoute";
import { AnalysisResultView } from "./AnalysisResultView";
import { DeleteAnalysisButton } from "./DeleteAnalysisButton";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; id: string; analysis: AnalysisResult }
  | { status: "not-found" }
  | { status: "session-gone" }
  | { status: "load-failed" };

function BackLink({ label }: { label: string }) {
  return (
    <Link
      href="/analyzer"
      className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
    >
      <ArrowLeft className="size-3.5" aria-hidden />
      {label}
    </Link>
  );
}

function NotFoundPanel() {
  return (
    <Container className="max-w-3xl py-10 sm:py-14">
      <BackLink label="Analyzer" />
      <h1 className="mt-4 text-3xl font-semibold tracking-[-0.02em]">Analysis not found</h1>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-ink-soft">
        It may have been deleted, or the link is wrong. Analyses are private to the account that
        created them.
      </p>
    </Container>
  );
}

function ReportContent() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (id === "") return;
    let cancelled = false;
    getAnalysis(id).then(
      (analysis) => {
        if (!cancelled) setState({ status: "ready", id, analysis });
      },
      (err: unknown) => {
        if (cancelled) return;
        if (
          err instanceof ApiRequestError &&
          (err.status === 404 || err.code === "validation_error")
        ) {
          setState({ status: "not-found" });
        } else if (isSessionGone(err)) {
          setState({ status: "session-gone" });
        } else {
          setState({ status: "load-failed" });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  // A missing id never fetches; a new id reuses this component (no remount),
  // so a stale ready state must not flash the old report.
  if (id === "") return <NotFoundPanel />;
  if (state.status === "loading" || (state.status === "ready" && state.id !== id)) {
    return (
      <Container className="max-w-3xl py-10 sm:py-14">
        <div
          aria-busy="true"
          aria-label="Loading analysis report"
          className="rounded-card border border-line bg-paper p-8"
        >
          <div className="animate-pulse space-y-3">
            <div className="h-6 w-48 rounded-lg bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-2/3 rounded bg-paper-deep" />
            <div className="h-24 w-full rounded-lg bg-paper-deep" />
          </div>
        </div>
      </Container>
    );
  }

  if (state.status === "not-found") return <NotFoundPanel />;

  if (state.status === "session-gone") {
    return (
      <Container className="max-w-3xl py-10 sm:py-14">
        <h1 className="mt-4 text-3xl font-semibold tracking-[-0.02em]">Session expired</h1>
        <p className="mt-3 max-w-xl text-base leading-relaxed text-ink-soft">
          Sign in again to view this analysis.
        </p>
        <p className="mt-5">
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
          >
            Sign in
          </Link>
        </p>
      </Container>
    );
  }

  if (state.status === "load-failed") {
    return (
      <Container className="max-w-3xl py-10 sm:py-14">
        <BackLink label="Analyzer" />
        <h1 className="mt-4 text-3xl font-semibold tracking-[-0.02em]">
          Couldn&apos;t load this analysis
        </h1>
        <p className="mt-3 max-w-xl text-base leading-relaxed text-ink-soft">
          Something went wrong fetching this report. The analysis itself is unaffected — try again.
        </p>
        <p className="mt-5">
          <button
            type="button"
            onClick={() => {
              setState({ status: "loading" });
              setAttempt((count) => count + 1);
            }}
            className="inline-flex items-center justify-center rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
          >
            Retry
          </button>
        </p>
      </Container>
    );
  }

  return (
    <Container className="max-w-3xl py-10 sm:py-14">
      <BackLink label="Analyzer" />
      <AnalysisResultView
        result={state.analysis}
        context="saved"
        onAiRetried={async () => {
          // Silent re-read: the effect below keeps the ready report rendered
          // while the fresh detail resolves (no skeleton flash).
          setAttempt((count) => count + 1);
        }}
        actions={
          <>
            <Link
              href="/analyzer"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              <ArrowLeft className="size-4" aria-hidden />
              Back to Analyzer
            </Link>
            <DeleteAnalysisButton analysisId={state.analysis.id} title={state.analysis.title} />
          </>
        }
      />
    </Container>
  );
}

export function AnalysisReportScreen() {
  return (
    <ProtectedRoute>
      <ReportContent />
    </ProtectedRoute>
  );
}
