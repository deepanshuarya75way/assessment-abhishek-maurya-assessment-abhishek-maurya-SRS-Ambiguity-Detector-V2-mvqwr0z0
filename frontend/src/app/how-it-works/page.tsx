import Link from "next/link";
import { Bot, FileInput, Gauge, ListTree, SearchCheck, UploadCloud } from "lucide-react";

import { Container } from "@/components/layout/Container";
import { JsonLd, PublicShell } from "@/components/public/PublicShell";
import { breadcrumbStructuredData, publicPageMetadata } from "@/lib/seo";

const title = "How SRS Ambiguity Detection Works";
const description =
  "See how SRS text or uploaded documents become segmented requirements, deterministic findings, scores, reports, and optional AI suggestions.";

export const metadata = publicPageMetadata({ title, description, path: "/how-it-works" });

const workflow = [
  {
    icon: FileInput,
    title: "1. Provide SRS text",
    copy: "Users can paste requirements directly into the analyzer. The text path is the simplest way to run the deterministic pipeline.",
  },
  {
    icon: UploadCloud,
    title: "2. Or upload a supported document",
    copy: "PDF, DOCX, and TXT uploads are validated, extracted, normalized, and then sent through the same analysis path as pasted text.",
  },
  {
    icon: ListTree,
    title: "3. Segment requirements",
    copy: "The service splits the normalized text into requirement units, preserving spans so reports can connect findings to the relevant text.",
  },
  {
    icon: SearchCheck,
    title: "4. Run deterministic detectors",
    copy: "Rule-based detectors inspect each requirement for the supported ambiguity categories. Each hit includes category, phrase, severity, reason, and recommendation.",
  },
  {
    icon: Gauge,
    title: "5. Calculate scores and report results",
    copy: "The application applies transparent severity deductions, computes score bands and health dimensions, and presents results in a private report.",
  },
  {
    icon: Bot,
    title: "6. Optionally enhance with AI",
    copy: "If configured, user-owned provider keys can request an overview and rewrite suggestions. AI output does not replace the deterministic score or findings.",
  },
];

export default function HowItWorksPage() {
  return (
    <PublicShell>
      <JsonLd
        data={breadcrumbStructuredData([
          { name: "Home", path: "/" },
          { name: "How it works", path: "/how-it-works" },
        ])}
      />
      <Container className="py-14 sm:py-20">
        <section className="max-w-4xl">
          <p className="font-mono text-xs tracking-[0.24em] text-signal uppercase">Workflow</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
            From SRS input to traceable ambiguity report.
          </h1>
          <p className="mt-5 text-lg leading-8 text-ink-soft">
            {description} The method is intentionally explainable: the core ambiguity score comes
            from deterministic detectors, not from an opaque model judgment.
          </p>
        </section>

        <section className="mt-12 grid gap-5" aria-label="Analysis workflow steps">
          {workflow.map((step) => {
            const Icon = step.icon;
            return (
              <article
                key={step.title}
                className="grid gap-5 rounded-2xl border border-line bg-white p-6 shadow-sm md:grid-cols-[auto_1fr] md:items-start"
              >
                <div className="flex size-12 items-center justify-center rounded-2xl bg-paper-deep">
                  <Icon className="size-6 text-signal" aria-hidden />
                </div>
                <div>
                  <h2 className="text-xl font-semibold">{step.title}</h2>
                  <p className="mt-2 leading-7 text-ink-soft">{step.copy}</p>
                </div>
              </article>
            );
          })}
        </section>

        <section
          className="mt-14 grid gap-6 lg:grid-cols-2"
          aria-label="Deterministic and AI boundaries"
        >
          <article className="rounded-[2rem] border border-line bg-white p-8 shadow-sm">
            <h2 className="text-2xl font-semibold tracking-tight">
              Deterministic analysis is the core
            </h2>
            <p className="mt-3 leading-7 text-ink-soft">
              The detector registry is the source of scoring. It identifies known ambiguity
              patterns, applies severity levels, and contributes directly to the score and health
              dimensions shown in the report.
            </p>
            <Link
              href="/resources/what-is-srs-ambiguity"
              className="mt-5 inline-flex text-sm font-semibold text-signal hover:text-signal-deep"
            >
              Learn about ambiguity categories
            </Link>
          </article>
          <article className="rounded-[2rem] border border-line bg-white p-8 shadow-sm">
            <h2 className="text-2xl font-semibold tracking-tight">AI assistance is optional</h2>
            <p className="mt-3 leading-7 text-ink-soft">
              AI enhancement can produce an overview and suggested rewrites only when a user
              configures a provider key. Provider output is treated as assistance, may be absent or
              fail, and does not change deterministic findings.
            </p>
            <Link
              href="/features"
              className="mt-5 inline-flex text-sm font-semibold text-signal hover:text-signal-deep"
            >
              Review implemented features
            </Link>
          </article>
        </section>

        <section
          className="mt-14 rounded-[2rem] border border-line bg-paper-deep p-8"
          aria-labelledby="limits-heading"
        >
          <h2 id="limits-heading" className="text-2xl font-semibold tracking-tight">
            Important limitations
          </h2>
          <ul className="mt-4 grid gap-3 leading-7 text-ink-soft">
            <li>
              The tool detects the currently implemented deterministic categories; it does not prove
              every requirement is correct.
            </li>
            <li>Scores are transparent heuristics for triage, not certified quality metrics.</li>
            <li>Documents are text-extracted from supported formats; OCR is not advertised.</li>
            <li>
              Human review remains necessary for domain intent, policy interpretation, and final
              acceptance criteria.
            </li>
          </ul>
        </section>
      </Container>
    </PublicShell>
  );
}
