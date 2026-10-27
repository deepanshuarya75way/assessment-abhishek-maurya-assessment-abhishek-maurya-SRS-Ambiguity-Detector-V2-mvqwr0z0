/** Canonical site metadata. Single source for layout, SEO, and footer copy. */

function normalizeSiteUrl(raw: string | undefined): string {
  const candidate = raw?.trim() || "http://localhost:3000";
  try {
    return new URL(candidate).origin;
  } catch {
    return "http://localhost:3000";
  }
}

export const SITE = {
  name: "SRS Ambiguity Detector",
  tagline: "Requirements ambiguity analysis for software teams.",
  description:
    "Find vague, incomplete, and unmeasurable software requirements with a deterministic SRS ambiguity analyzer. Keep private history and explain every finding.",
  url: normalizeSiteUrl(process.env.NEXT_PUBLIC_SITE_URL),
} as const;
