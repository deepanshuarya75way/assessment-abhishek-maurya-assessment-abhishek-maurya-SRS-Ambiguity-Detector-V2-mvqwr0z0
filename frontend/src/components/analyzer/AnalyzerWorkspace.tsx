"use client";

/**
 * `/analyzer` workspace (Stage 08): the first private product surface.
 * Verified-users-only (`ProtectedRoute requireVerified` — the API gates the
 * same way). Two input methods — pasted text or an uploaded PDF/DOCX/TXT
 * file — both running the SAME deterministic pipeline. Owns the input→result
 * state: submitting swaps the editor for the scored analysis result;
 * starting over returns to the same tab WITH the last submission preserved
 * as a resumable draft (the file itself cannot persist — only its title).
 */

import Link from "next/link";
import { useRef, useState } from "react";

import { ArrowLeft, ArrowRight } from "lucide-react";

import type { AnalysisResult } from "@/types/analysis";
import { Container } from "@/components/layout/Container";
import { Reveal } from "@/components/Reveal";
import { getAnalysis } from "@/lib/analysis";
import { cn } from "@/lib/utils";

import { ProtectedRoute } from "../auth/ProtectedRoute";
import { AnalysisResultView } from "./AnalysisResultView";
import { AnalyzerForm, type AnalyzerDraft } from "./AnalyzerForm";
import { DocumentUploadForm } from "./DocumentUploadForm";

type InputMode = "paste" | "upload";

const TABS: { id: InputMode; label: string }[] = [
  { id: "paste", label: "Paste text" },
  { id: "upload", label: "Upload file" },
];

export function AnalyzerWorkspace() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [mode, setMode] = useState<InputMode>("paste");
  const [draft, setDraft] = useState<AnalyzerDraft | undefined>(undefined);
  const [uploadTitle, setUploadTitle] = useState("");
  const tabRefs = useRef<Record<InputMode, HTMLButtonElement | null>>({
    paste: null,
    upload: null,
  });

  // Automatic-activation tabs: arrows move selection AND focus.
  function handleTabKeyDown(event: React.KeyboardEvent) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = TABS.findIndex((tab) => tab.id === mode);
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = TABS[(index + delta + TABS.length) % TABS.length];
    if (next === undefined) return; // unreachable: modulo keeps the index in range
    setMode(next.id);
    tabRefs.current[next.id]?.focus();
  }

  return (
    <ProtectedRoute>
      <Container className="max-w-3xl py-10 sm:py-14">
        <Reveal>
          <p className="font-mono text-xs tracking-[0.2em] text-signal uppercase">Analyzer</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.02em] text-balance sm:text-4xl">
            Analyze requirements
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-soft">
            Paste your SRS text below, or upload a PDF, DOCX, or TXT file. Either way we split it
            into individual requirements — numbered, bulleted, ID-tagged, or plain paragraphs — then
            run the deterministic ambiguity detectors over each one and score the set.
          </p>
          <p className="mt-4">
            <Link
              href="/history"
              className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              View history
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </p>
        </Reveal>

        {result === null ? (
          <>
            <div
              role="tablist"
              aria-label="Input method"
              onKeyDown={handleTabKeyDown}
              className="mt-8 inline-flex gap-1 rounded-full border border-line bg-paper-deep p-1"
            >
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  ref={(node) => {
                    tabRefs.current[tab.id] = node;
                  }}
                  role="tab"
                  id={`analyzer-tab-${tab.id}`}
                  aria-selected={mode === tab.id}
                  aria-controls={`analyzer-panel-${tab.id}`}
                  tabIndex={mode === tab.id ? 0 : -1}
                  onClick={() => setMode(tab.id)}
                  className={cn(
                    "rounded-full px-5 py-2 text-[14px] font-medium transition outline-none focus-visible:ring-2 focus-visible:ring-signal/50",
                    mode === tab.id
                      ? "bg-white text-ink shadow-sm"
                      : "text-ink-soft hover:text-ink",
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div
              role="tabpanel"
              id={`analyzer-panel-${mode}`}
              aria-labelledby={`analyzer-tab-${mode}`}
            >
              {mode === "paste" ? (
                <AnalyzerForm
                  initial={draft}
                  onResult={(analysis, submitted) => {
                    setResult(analysis);
                    setDraft(submitted);
                  }}
                />
              ) : (
                <DocumentUploadForm
                  initial={{ title: uploadTitle }}
                  onResult={(analysis, submitted) => {
                    setResult(analysis);
                    setUploadTitle(submitted.title);
                  }}
                />
              )}
            </div>
          </>
        ) : (
          <AnalysisResultView
            result={result}
            onAiRetried={async (analysisId) => {
              // Silent re-read: the just-analyzed report stays rendered while
              // the post-retry detail resolves. Rejections propagate to the
              // retry control (mapped copy), never to a crash.
              setResult(await getAnalysis(analysisId));
            }}
            actions={
              <button
                type="button"
                onClick={() => setResult(null)}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition hover:bg-paper-deep"
              >
                <ArrowLeft className="size-4" aria-hidden />
                Start over
              </button>
            }
          />
        )}
      </Container>
    </ProtectedRoute>
  );
}
