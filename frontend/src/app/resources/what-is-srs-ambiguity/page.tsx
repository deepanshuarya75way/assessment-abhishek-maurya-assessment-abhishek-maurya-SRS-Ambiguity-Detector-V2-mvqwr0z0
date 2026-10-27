import Link from "next/link";
import { AlertTriangle, ArrowRight } from "lucide-react";

import { Container } from "@/components/layout/Container";
import { JsonLd, PublicShell } from "@/components/public/PublicShell";
import { DETECTED_AMBIGUITY_CATEGORIES } from "@/lib/public-content";
import { articleStructuredData, breadcrumbStructuredData, publicPageMetadata } from "@/lib/seo";

const title = "What Is SRS Ambiguity?";
const description =
  "Understand ambiguity in Software Requirements Specifications, common detected categories, examples, risks, and clarification patterns.";
const path = "/resources/what-is-srs-ambiguity";

export const metadata = publicPageMetadata({ title, description, path });

export default function WhatIsSrsAmbiguityPage() {
  return (
    <PublicShell>
      <JsonLd
        data={[
          breadcrumbStructuredData([
            { name: "Home", path: "/" },
            { name: "Resources", path: "/resources" },
            { name: "What is SRS ambiguity?", path },
          ]),
          articleStructuredData({ title, description, path }),
        ]}
      />
      <Container className="py-14 sm:py-20">
        <article className="mx-auto max-w-4xl">
          <p className="font-mono text-xs tracking-[0.24em] text-signal uppercase">Guide</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
            What is ambiguity in a Software Requirements Specification?
          </h1>
          <p className="mt-5 text-lg leading-8 text-ink-soft">
            SRS ambiguity appears when a requirement can reasonably be interpreted in more than one
            way, cannot be objectively tested, or omits information needed for implementation.
            Ambiguity does not always mean the requirement is wrong, but it signals that teams
            should clarify the statement before relying on it.
          </p>

          <section
            className="mt-10 rounded-[2rem] border border-line bg-paper-deep p-8"
            aria-labelledby="human-review-heading"
          >
            <AlertTriangle className="size-7 text-gold-deep" aria-hidden />
            <h2 id="human-review-heading" className="mt-4 text-2xl font-semibold tracking-tight">
              Detected categories are not the whole universe of ambiguity
            </h2>
            <p className="mt-3 leading-7 text-ink-soft">
              The deterministic engine currently detects the categories below. Broader questions —
              domain intent, regulatory interpretation, product strategy, or stakeholder priority —
              still require human review. The tool is a review aid, not a guarantee that an SRS is
              complete or correct.
            </p>
          </section>

          <section className="mt-12" aria-labelledby="categories-heading">
            <h2 id="categories-heading" className="text-3xl font-semibold tracking-tight">
              Categories currently detected by the deterministic engine
            </h2>
            <div className="mt-6 grid gap-5">
              {DETECTED_AMBIGUITY_CATEGORIES.map((category) => (
                <section
                  key={category.detectorId}
                  className="rounded-2xl border border-line bg-white p-6 shadow-sm"
                  aria-labelledby={`${category.detectorId}-heading`}
                >
                  <p className="font-mono text-xs text-ink-faint">{category.detectorId}</p>
                  <h3 id={`${category.detectorId}-heading`} className="mt-2 text-xl font-semibold">
                    {category.name}
                  </h3>
                  <p className="mt-3 leading-7 text-ink-soft">{category.explanation}</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    <div className="rounded-xl bg-paper-deep p-4">
                      <p className="text-sm font-semibold">Synthetic example</p>
                      <p className="mt-2 text-sm leading-6 text-ink-soft">{category.example}</p>
                    </div>
                    <div className="rounded-xl bg-paper-deep p-4">
                      <p className="text-sm font-semibold">Why it can confuse</p>
                      <p className="mt-2 text-sm leading-6 text-ink-soft">{category.risk}</p>
                    </div>
                    <div className="rounded-xl bg-paper-deep p-4">
                      <p className="text-sm font-semibold">Clarification pattern</p>
                      <p className="mt-2 text-sm leading-6 text-ink-soft">
                        {category.clarification}
                      </p>
                    </div>
                  </div>
                </section>
              ))}
            </div>
          </section>

          <section
            className="mt-12 rounded-[2rem] border border-line bg-white p-8 shadow-sm"
            aria-labelledby="next-heading"
          >
            <h2 id="next-heading" className="text-2xl font-semibold tracking-tight">
              Next step: review how findings become a report
            </h2>
            <p className="mt-3 leading-7 text-ink-soft">
              The analyzer ties findings to requirement text, applies severity-based scoring, and
              shows recommendations so teams can decide which requirements need clarification.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/how-it-works"
                className="inline-flex items-center gap-2 rounded-input bg-ink px-4 py-2 text-sm font-semibold text-paper hover:bg-black"
              >
                See how it works <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link
                href="/resources/write-clearer-requirements"
                className="rounded-input border border-line px-4 py-2 text-sm font-semibold hover:bg-paper-deep"
              >
                Learn to write clearer requirements
              </Link>
            </div>
          </section>
        </article>
      </Container>
    </PublicShell>
  );
}
