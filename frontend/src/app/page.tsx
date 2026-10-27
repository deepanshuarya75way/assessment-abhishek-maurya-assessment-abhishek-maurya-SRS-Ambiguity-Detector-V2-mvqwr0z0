import Link from "next/link";
import { ArrowRight, CheckCircle2, FileText, LockKeyhole, ShieldCheck } from "lucide-react";

import { Container } from "@/components/layout/Container";
import { JsonLd, PublicShell } from "@/components/public/PublicShell";
import { homeStructuredData, publicPageMetadata } from "@/lib/seo";
import { SITE } from "@/lib/site";

export const metadata = publicPageMetadata({
  title: `${SITE.name} — Requirements ambiguity analysis`,
  description: SITE.description,
  path: "/",
});

const highlights = [
  "Analyze pasted SRS text or supported PDF, DOCX, and TXT documents.",
  "Review deterministic findings with categories, severity, reasons, and recommendations.",
  "Keep saved reports, history, dashboard statistics, and provider settings private.",
];

const capabilities = [
  {
    icon: FileText,
    title: "SRS-focused analysis",
    copy: "Segment requirements, inspect wording, and surface ambiguity patterns before review meetings or implementation planning.",
  },
  {
    icon: CheckCircle2,
    title: "Traceable findings",
    copy: "Each issue identifies the phrase, detector category, severity, reason, and recommendation used to improve the requirement.",
  },
  {
    icon: LockKeyhole,
    title: "Private by default",
    copy: "Analysis workspace, saved reports, dashboard, history, and settings are authenticated and marked noindex.",
  },
];

export default function HomePage() {
  return (
    <PublicShell>
      <JsonLd data={homeStructuredData()} />
      <Container className="py-16 sm:py-20 lg:py-24">
        <section className="grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <p className="font-mono text-xs tracking-[0.24em] text-signal uppercase">
              SRS ambiguity detection
            </p>
            <h1 className="mt-4 max-w-4xl text-4xl leading-tight font-semibold tracking-tight sm:text-5xl lg:text-6xl">
              Find unclear software requirements before they become rework.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-ink-soft">
              {SITE.name} reviews Software Requirements Specifications for vague, incomplete,
              subjective, and hard-to-test language. The core score comes from a deterministic rule
              engine; optional AI can add overview and rewrite assistance when users configure their
              own provider.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/signup"
                className="inline-flex items-center justify-center gap-2 rounded-input bg-ink px-5 py-3 text-sm font-semibold text-paper shadow-sm transition hover:-translate-y-px hover:bg-black"
              >
                Start analyzing <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link
                href="/how-it-works"
                className="inline-flex items-center justify-center rounded-input border border-line bg-white px-5 py-3 text-sm font-semibold transition hover:-translate-y-px hover:shadow-sm"
              >
                Learn how it works
              </Link>
            </div>
            <ul className="mt-8 grid gap-3 text-sm text-ink-soft" aria-label="Product highlights">
              {highlights.map((highlight) => (
                <li key={highlight} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden />
                  <span>{highlight}</span>
                </li>
              ))}
            </ul>
          </div>

          <aside
            className="rounded-[2rem] border border-line bg-white p-6 shadow-xl shadow-ink/5"
            aria-label="Example ambiguity finding summary"
          >
            <div className="rounded-2xl bg-paper-deep p-5">
              <p className="font-mono text-xs tracking-[0.2em] text-ink-faint uppercase">
                Example check
              </p>
              <p className="mt-4 text-lg font-semibold">
                “The system should be fast and user friendly.”
              </p>
              <div className="mt-5 space-y-3">
                <div className="rounded-xl border border-line bg-white p-4">
                  <p className="text-sm font-semibold text-sev-high">Subjective term</p>
                  <p className="mt-1 text-sm leading-6 text-ink-soft">
                    “Fast” needs a measurable threshold such as response time, throughput, or
                    operating load.
                  </p>
                </div>
                <div className="rounded-xl border border-line bg-white p-4">
                  <p className="text-sm font-semibold text-sev-medium">
                    Missing measurable criteria
                  </p>
                  <p className="mt-1 text-sm leading-6 text-ink-soft">
                    “User friendly” should reference usability criteria or acceptance tests.
                  </p>
                </div>
              </div>
            </div>
            <p className="mt-5 flex items-start gap-2 text-sm leading-6 text-ink-soft">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden />
              Public content uses synthetic examples only. Private reports never expose user SRS
              text, document names, analysis IDs, provider credentials, or tokenized URLs.
            </p>
          </aside>
        </section>

        <section
          className="mt-16 grid gap-4 border-t border-line pt-10 md:grid-cols-3"
          aria-labelledby="capabilities-heading"
        >
          <h2 id="capabilities-heading" className="sr-only">
            Product capabilities
          </h2>
          {capabilities.map((item) => {
            const Icon = item.icon;
            return (
              <article
                key={item.title}
                className="rounded-2xl border border-line bg-white p-6 shadow-sm"
              >
                <Icon className="size-6 text-signal" aria-hidden />
                <h3 className="mt-4 text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-ink-soft">{item.copy}</p>
              </article>
            );
          })}
        </section>

        <section
          className="mt-16 rounded-[2rem] border border-line bg-white p-8 shadow-sm"
          aria-labelledby="learn-more-heading"
        >
          <h2 id="learn-more-heading" className="text-2xl font-semibold tracking-tight">
            Explore the method behind the score
          </h2>
          <p className="mt-3 max-w-3xl leading-7 text-ink-soft">
            The public guides explain what the deterministic engine checks, how scores and health
            dimensions are interpreted, and where human review still matters.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/features"
              className="rounded-input border border-line px-4 py-2 text-sm font-semibold hover:bg-paper-deep"
            >
              See features
            </Link>
            <Link
              href="/resources"
              className="rounded-input border border-line px-4 py-2 text-sm font-semibold hover:bg-paper-deep"
            >
              Read resources
            </Link>
          </div>
        </section>
      </Container>
    </PublicShell>
  );
}
