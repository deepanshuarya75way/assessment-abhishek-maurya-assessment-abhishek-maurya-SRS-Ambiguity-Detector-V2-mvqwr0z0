import type { MetadataRoute } from "next";

import { robotsPolicy } from "@/lib/seo";

/** Public crawler policy. Page-level noindex remains the protection for private routes. */
export default function robots(): MetadataRoute.Robots {
  return robotsPolicy();
}
