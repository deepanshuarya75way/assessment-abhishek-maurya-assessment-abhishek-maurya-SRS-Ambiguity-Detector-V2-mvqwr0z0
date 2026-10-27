import Link from "next/link";
import {
  BarChart3,
  Bot,
  FileText,
  Gauge,
  History,
  ListChecks,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { Container } from "@/components/layout/Container";
import { JsonLd, PublicShell } from "@/components/public/PublicShell";
import { HEALTH_DIMENSIONS } from "@/lib/public-content";
import { breadcrumbStructuredData, publicPageMetadata } from "@/lib/seo";

const title = "SRS Ambiguity Detection Features";
const description =
  "Explore deterministic SRS analysis, document upload, scoring, reports, history, dashboards, and optional AI assistance.";

export const metadata = publicPageMetadata({ title, description, path: "/features" });

const features = [
  {
    icon: FileText,
    title: "Text and document analysis",
    copy: "Paste SRS text directly or upload one supported PDF, DOCX, or TXT document. Uploaded files are validated before text extraction and analysis.",
  },
  {
    icon: ListChecks,
    title: "Requirement segmentation",
    copy: "The service normalizes input and splits it into requirement-sized units so each finding can be tied back to a specific requirement.",
  },
  {
    icon: Gauge,
    title: "Deterministic ambiguity detection",
    copy: "Rule-based detectors identify currently supported ambiguity categories and produce phrase evidence, severity, reasons, and recommendations.",
  },
  {
    icon: BarChart3,
    title: "Transparent scoring",
    copy: "Scores start at 100 and apply severity-based deductions. Health dimensions summarize measurability, specificity, clarity, and completeness.",
  },
  {
    icon: Bot,
    title: "Optional AI enhancement",
    copy: "When a user configures their own provider key, AI can add an overview and rewrite suggestions. The deterministic findings and score remain the core result.",
  },
  {
    icon: History,
    title: "Private history and dashboard",
    copy: "Saved analyses, recent activity, trends, distributions, and settings live behind authentication and stay excluded from public indexing.",
  },
];

export default function FeaturesPage() {
  return (
    <PublicShell>
      <JsonLd
        data={breadcrumbStructuredData([
          { name: "Home", path: "/" },
          { name: "Features", path: "/features" },
        ])}
      />
      <Container className="py-14 sm:py-20">
        <section className="max-w-4xl">
          <p className="font-mono text-xs tracking-[0.24em] text-signal uppercase">Features</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
            Requirements review features built around traceable ambiguity findings.
          </h1>
          <p className="mt-5 text-lg leading-8 text-ink-soft">
            {description} The product is useful without AI: deterministic analysis is always the
            foundation, while AI output is an optional aid for users who configure provider access.
          </p>
        </section>

        <section
          className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3"
          aria-label="Implemented product capabilities"
        >
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <article
                key={feature.title}
                className="rounded-2xl border border-line bg-white p-6 shadow-sm"
              >
                <Icon className="size-6 text-signal" aria-hidden />
                <h2 className="mt-4 text-xl font-semibold">{feature.title}</h2>
                <p className="mt-3 text-sm leading-6 text-ink-soft">{feature.copy}</p>
              </article>
            );
          })}
        </section>

        <section
          className="mt-14 grid gap-8 rounded-[2rem] border border-line bg-white p-8 shadow-sm lg:grid-cols-[0.9fr_1.1fr]"
          aria-labelledby="score-heading"
        >
          <div>
            <Gauge className="size-8 text-signal" aria-hidden />
            <h2 id="score-heading" className="mt-4 text-2xl font-semibold tracking-tight">
              What the score means
            </h2>
            <p className="mt-3 leading-7 text-ink-soft">
              The ambiguity score is an application-generated heuristic, not a universal industry
              metric. It is designed to help teams triage review effort and inspect the findings
              that caused deductions.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {HEALTH_DIMENSIONS.map((dimension) => (
              <div key={dimension.name} className="rounded-2xl bg-paper-deep p-5">
                <h3 className="font-semibold">{dimension.name}</h3>
                <p className="mt-2 text-sm leading-6 text-ink-soft">{dimension.copy}</p>
              </div>
            ))}
          </div>
        </section>

        <section
          className="mt-14 rounded-[2rem] border border-line bg-ink p-8 text-paper"
          aria-labelledby="privacy-heading"
        >
          <ShieldCheck className="size-8 text-gold" aria-hidden />
          <h2 id="privacy-heading" className="mt-4 text-2xl font-semibold tracking-tight">
            Public pages explain the product. They do not expose the product data.
          </h2>
          <p className="mt-3 max-w-3xl leading-7 text-paper/75">
            Analysis reports, uploads, history, dashboards, provider keys, privacy controls, and
            account settings remain authenticated application surfaces. Public pages use only
            synthetic examples and generic product information.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/how-it-works"
              className="rounded-input bg-paper px-4 py-2 text-sm font-semibold text-ink"
            >
              See the workflow
            </Link>
            <Link
              href="/signup"
              className="rounded-input border border-paper/30 px-4 py-2 text-sm font-semibold text-paper"
            >
              Get started
            </Link>
          </div>
        </section>

        <section
          className="mt-14 rounded-[2rem] border border-line bg-white p-8 shadow-sm"
          aria-labelledby="document-heading"
        >
          <Upload className="size-8 text-signal" aria-hidden />
          <h2 id="document-heading" className="mt-4 text-2xl font-semibold tracking-tight">
            Document workflow, accurately scoped
          </h2>
          <p className="mt-3 max-w-3xl leading-7 text-ink-soft">
            The current upload pipeline supports PDF, DOCX, and TXT files. It validates file type,
            extracts text, applies the same analysis pipeline as pasted text, and supports private
            document list, purge, and short-lived download URL workflows for authenticated users. It
            does not claim OCR support or universal parsing of every document shape.
          </p>
        </section>
      </Container>
    </PublicShell>
  );
}
