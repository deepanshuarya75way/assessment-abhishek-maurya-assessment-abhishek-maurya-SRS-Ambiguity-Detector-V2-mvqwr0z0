import Link from "next/link";
import { ArrowRight, BookOpen, CheckCircle2 } from "lucide-react";

import { Container } from "@/components/layout/Container";
import { JsonLd, PublicShell } from "@/components/public/PublicShell";
import { RESOURCE_CARDS } from "@/lib/public-content";
import { breadcrumbStructuredData, publicPageMetadata } from "@/lib/seo";

const title = "SRS Ambiguity Resources";
const description =
  "Educational guides for understanding ambiguity in Software Requirements Specifications and writing clearer requirements.";

export const metadata = publicPageMetadata({ title, description, path: "/resources" });

const reviewChecklist = [
  "Can a tester objectively decide whether the requirement passed?",
  "Are actors, systems, and responsibilities named directly?",
  "Are quantities, time limits, formats, and constraints explicit?",
  "Are optional behaviors separated from mandatory ones?",
];

export default function ResourcesPage() {
  return (
    <PublicShell>
      <JsonLd
        data={breadcrumbStructuredData([
          { name: "Home", path: "/" },
          { name: "Resources", path: "/resources" },
        ])}
      />
      <Container className="py-14 sm:py-20">
        <section className="max-w-4xl">
          <p className="font-mono text-xs tracking-[0.24em] text-signal uppercase">Resources</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
            Practical guides for clearer Software Requirements Specifications.
          </h1>
          <p className="mt-5 text-lg leading-8 text-ink-soft">
            {description} These pages use synthetic examples and connect back to the actual
            deterministic categories supported by the product.
          </p>
        </section>

        <section className="mt-12 grid gap-5 md:grid-cols-2" aria-label="Educational resources">
          {RESOURCE_CARDS.map((resource) => (
            <article
              key={resource.href}
              className="rounded-[2rem] border border-line bg-white p-8 shadow-sm"
            >
              <BookOpen className="size-7 text-signal" aria-hidden />
              <h2 className="mt-4 text-2xl font-semibold tracking-tight">{resource.title}</h2>
              <p className="mt-3 leading-7 text-ink-soft">{resource.summary}</p>
              <Link
                href={resource.href}
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-signal hover:text-signal-deep"
              >
                Read the guide <ArrowRight className="size-4" aria-hidden />
              </Link>
            </article>
          ))}
        </section>

        <section
          className="mt-14 rounded-[2rem] border border-line bg-paper-deep p-8"
          aria-labelledby="quick-review-heading"
        >
          <h2 id="quick-review-heading" className="text-2xl font-semibold tracking-tight">
            Quick SRS review questions
          </h2>
          <ul className="mt-5 grid gap-3 text-ink-soft md:grid-cols-2">
            {reviewChecklist.map((item) => (
              <li key={item} className="flex gap-3">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/how-it-works"
              className="rounded-input border border-line bg-white px-4 py-2 text-sm font-semibold hover:bg-paper"
            >
              How the analyzer works
            </Link>
            <Link
              href="/signup"
              className="rounded-input bg-ink px-4 py-2 text-sm font-semibold text-paper hover:bg-black"
            >
              Start analyzing
            </Link>
          </div>
        </section>
      </Container>
    </PublicShell>
  );
}
