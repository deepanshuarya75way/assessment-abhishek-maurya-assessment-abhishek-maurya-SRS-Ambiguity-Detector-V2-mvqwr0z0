"use client";

/**
 * Home-page entry to `/analyzer`, visible ONLY to signed-in users; public
 * visitors use the normal marketing CTAs.
 */

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";

export function AnalyzerEntryLink() {
  const { status } = useAuth();
  if (status !== "authenticated") return null;
  return (
    <Link
      href="/analyzer"
      className="inline-flex items-center gap-1 rounded-full bg-signal px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-signal-deep"
    >
      Open analyzer <ArrowUpRight className="size-4" aria-hidden />
    </Link>
  );
}
