import Link from "next/link";

import { Container } from "@/components/layout/Container";
import { privatePageMetadata } from "@/lib/seo";

export const metadata = privatePageMetadata(
  "Page not found",
  "The requested page could not be found.",
);

/** Branded 404 for unknown app routes; safe copy only, no IDs or diagnostics. */
export default function NotFound() {
  return (
    <Container className="flex min-h-dvh max-w-2xl flex-col items-start justify-center">
      <p className="font-mono text-xs tracking-[0.2em] text-signal uppercase">404</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">
        This section isn&apos;t specified.
      </h1>
      <p className="mt-3 leading-relaxed text-ink-soft">
        Unlike a good requirement, this URL is ambiguous — it doesn&apos;t point anywhere.
        Let&apos;s return to something measurable.
      </p>
      <Link
        href="/"
        className="mt-6 rounded-input bg-ink px-5 py-2.5 text-sm font-medium text-paper transition-transform duration-120 hover:-translate-y-px"
      >
        Back to home
      </Link>
    </Container>
  );
}
