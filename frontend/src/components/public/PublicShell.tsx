import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AnalyzerEntryLink } from "@/components/analyzer/AnalyzerEntryLink";
import { Container } from "@/components/layout/Container";
import { PUBLIC_CONTENT_ROUTES } from "@/lib/public-content";
import { SITE } from "@/lib/site";

const primaryLinks = PUBLIC_CONTENT_ROUTES.filter((route) =>
  ["/features", "/how-it-works", "/resources"].includes(route.path),
);

export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-dvh bg-paper text-ink">
      <header className="border-b border-line/70 bg-paper/95">
        <Container className="py-5">
          <nav
            className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"
            aria-label="Primary"
          >
            <div className="flex items-center justify-between gap-4">
              <Link href="/" className="font-serif text-xl font-semibold tracking-tight">
                {SITE.name}
              </Link>
              <Link
                href="/signup"
                className="rounded-full border border-line bg-white px-4 py-2 text-sm font-semibold shadow-sm transition hover:-translate-y-px hover:shadow md:hidden"
              >
                Get started
              </Link>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-sm font-medium text-ink-soft">
              {primaryLinks.map((link) => (
                <Link key={link.path} href={link.path} className="hover:text-ink">
                  {link.label}
                </Link>
              ))}
              <AnalyzerEntryLink />
              <Link href="/login" className="hover:text-ink">
                Log in
              </Link>
              <Link
                href="/signup"
                className="hidden rounded-full border border-line bg-white px-4 py-2 font-semibold shadow-sm transition hover:-translate-y-px hover:shadow md:inline-flex"
              >
                Get started
              </Link>
            </div>
          </nav>
        </Container>
      </header>
      {children}
      <footer className="border-t border-line bg-white">
        <Container className="grid gap-8 py-10 md:grid-cols-[1.2fr_0.8fr_0.8fr]">
          <div>
            <p className="font-serif text-lg font-semibold">{SITE.name}</p>
            <p className="mt-3 max-w-md text-sm leading-6 text-ink-soft">
              Public pages explain the product and requirements-review method. Private analysis,
              history, dashboard, settings, and reports remain authenticated and noindex.
            </p>
          </div>
          <div>
            <h2 className="text-sm font-semibold">Public content</h2>
            <ul className="mt-3 space-y-2 text-sm text-ink-soft">
              {primaryLinks.map((link) => (
                <li key={link.path}>
                  <Link href={link.path} className="hover:text-ink">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="text-sm font-semibold">Use the app</h2>
            <ul className="mt-3 space-y-2 text-sm text-ink-soft">
              <li>
                <Link href="/signup" className="inline-flex items-center gap-1 hover:text-ink">
                  Create an account <ArrowRight className="size-3" aria-hidden />
                </Link>
              </li>
              <li>
                <Link href="/login" className="hover:text-ink">
                  Log in
                </Link>
              </li>
            </ul>
          </div>
        </Container>
      </footer>
    </main>
  );
}

export function JsonLd({
  data,
}: {
  data: Record<string, unknown> | Array<Record<string, unknown>>;
}) {
  return <script type="application/ld+json">{JSON.stringify(data)}</script>;
}
