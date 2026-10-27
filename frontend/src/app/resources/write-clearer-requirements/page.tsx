import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";

import { Container } from "@/components/layout/Container";
import { JsonLd, PublicShell } from "@/components/public/PublicShell";
import { HEALTH_DIMENSIONS } from "@/lib/public-content";
import { articleStructuredData, breadcrumbStructuredData, publicPageMetadata } from "@/lib/seo";

const title = "How to Write Clearer Software Requirements";
const description =
  "Use practical patterns to make SRS requirements more measurable, specific, clear, and complete before implementation.";
const path = "/resources/write-clearer-requirements";

export const metadata = publicPageMetadata({ title, description, path });

const examples = [
  {
    weak: "The system shall respond quickly.",
    clearer:
      "The system shall return the account dashboard within 2 seconds for 95% of requests under normal operating load.",
    why: "The clearer version defines behavior, threshold, percentage, and condition.",
  },
  {
    weak: "Reports may be exported when necessary.",
    clearer:
      "Administrators shall be able to export monthly reports as CSV and PDF from the Reports page.",
    why: "The clearer version removes optional language and names the actor, formats, and location.",
  },
  {
    weak: "The standard workflow shall be followed.",
    clearer: "The approval workflow shall follow Policy FIN-12, steps 1–5, before payment release.",
    why: "The clearer version replaces undefined terminology with a specific reference.",
  },
];

export default function WriteClearerRequirementsPage() {
  return (
    <PublicShell>
      <JsonLd
        data={[
          breadcrumbStructuredData([
            { name: "Home", path: "/" },
            { name: "Resources", path: "/resources" },
            { name: "Write clearer requirements", path },
          ]),
          articleStructuredData({ title, description, path }),
        ]}
      />
      <Container className="py-14 sm:py-20">
        <article className="mx-auto max-w-4xl">
          <p className="font-mono text-xs tracking-[0.24em] text-signal uppercase">Guide</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
            How to write clearer software requirements before development starts.
          </h1>
          <p className="mt-5 text-lg leading-8 text-ink-soft">
            Clear requirements make implementation and testing easier because readers can identify
            the actor, behavior, condition, constraints, and acceptance signal. The goal is not to
            make every sentence longer; it is to make every important decision explicit enough to
            review.
          </p>

          <section className="mt-10 grid gap-4 md:grid-cols-2" aria-labelledby="dimensions-heading">
            <div>
              <h2 id="dimensions-heading" className="text-2xl font-semibold tracking-tight">
                Four review dimensions
              </h2>
              <p className="mt-3 leading-7 text-ink-soft">
                These dimensions mirror how the product groups detector effects in analysis reports.
                They are useful as a human review checklist too.
              </p>
            </div>
            <div className="grid gap-3">
              {HEALTH_DIMENSIONS.map((dimension) => (
                <div
                  key={dimension.name}
                  className="rounded-2xl border border-line bg-white p-5 shadow-sm"
                >
                  <h3 className="font-semibold">{dimension.name}</h3>
                  <p className="mt-2 text-sm leading-6 text-ink-soft">{dimension.copy}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-12" aria-labelledby="patterns-heading">
            <h2 id="patterns-heading" className="text-3xl font-semibold tracking-tight">
              Rewrite patterns that usually improve requirements
            </h2>
            <ul className="mt-5 grid gap-3 leading-7 text-ink-soft">
              <li className="flex gap-3">
                <CheckCircle2 className="mt-1 size-4 shrink-0 text-signal" aria-hidden />
                Name the actor or system component responsible for the behavior.
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="mt-1 size-4 shrink-0 text-signal" aria-hidden />
                Replace vague adjectives with thresholds, ranges, or acceptance criteria.
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="mt-1 size-4 shrink-0 text-signal" aria-hidden />
                Replace open-ended lists with the exact required set.
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="mt-1 size-4 shrink-0 text-signal" aria-hidden />
                Define domain terms or link them to a controlled glossary, policy, or source
                document.
              </li>
              <li className="flex gap-3">
                <CheckCircle2 className="mt-1 size-4 shrink-0 text-signal" aria-hidden />
                Separate mandatory behavior from optional or future behavior.
              </li>
            </ul>
          </section>

          <section className="mt-12" aria-labelledby="examples-heading">
            <h2 id="examples-heading" className="text-3xl font-semibold tracking-tight">
              Vague vs measurable examples
            </h2>
            <div className="mt-6 grid gap-5">
              {examples.map((example) => (
                <article
                  key={example.weak}
                  className="rounded-2xl border border-line bg-white p-6 shadow-sm"
                >
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="rounded-xl bg-paper-deep p-4">
                      <h3 className="font-semibold text-sev-high">Needs clarification</h3>
                      <p className="mt-2 text-sm leading-6 text-ink-soft">{example.weak}</p>
                    </div>
                    <div className="rounded-xl bg-paper-deep p-4">
                      <h3 className="font-semibold text-signal">Clearer direction</h3>
                      <p className="mt-2 text-sm leading-6 text-ink-soft">{example.clearer}</p>
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-ink-soft">{example.why}</p>
                </article>
              ))}
            </div>
          </section>

          <section
            className="mt-12 rounded-[2rem] border border-line bg-ink p-8 text-paper"
            aria-labelledby="cta-heading"
          >
            <h2 id="cta-heading" className="text-2xl font-semibold tracking-tight">
              Use automated review as a second pass, not a replacement for collaboration.
            </h2>
            <p className="mt-3 leading-7 text-paper/75">
              The analyzer can highlight common ambiguity patterns and explain why a requirement may
              need clarification. Product owners, engineers, QA, and stakeholders still decide the
              intended behavior and business constraints.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 rounded-input bg-paper px-4 py-2 text-sm font-semibold text-ink"
              >
                Start analyzing <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link
                href="/resources/what-is-srs-ambiguity"
                className="rounded-input border border-paper/30 px-4 py-2 text-sm font-semibold text-paper"
              >
                Review ambiguity categories
              </Link>
            </div>
          </section>
        </article>
      </Container>
    </PublicShell>
  );
}
