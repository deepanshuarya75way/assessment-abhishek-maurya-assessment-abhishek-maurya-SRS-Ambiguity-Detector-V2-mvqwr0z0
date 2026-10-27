import type { MetadataRoute } from "next";

import { sitemapEntries } from "@/lib/seo";

/** Public routes only. Never include auth, private app, token, or analysis-detail URLs. */
export default function sitemap(): MetadataRoute.Sitemap {
  return sitemapEntries();
}
