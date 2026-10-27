import type { NextConfig } from "next";

import { buildReportOnlyCsp } from "./src/lib/csp";

// Security headers posture (the project contract). Framing denial applies ONLY in
// production so sandboxed/preview iframes keep working during development.
const isProd = process.env.APP_ENV === "production" || process.env.VERCEL_ENV === "production";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    const headers: { key: string; value: string }[] = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ];
    if (isProd) {
      headers.push({ key: "X-Frame-Options", value: "DENY" });
      headers.push({
        key: "Content-Security-Policy",
        value: "frame-ancestors 'none'",
      });
      // Full CSP (Stage 20, roadmap-21): report-only first — violations are logged
      // without breaking the app; tune from real-browser data before enforcing.
      // The enforced framing directive above stays (clickjacking is already solved).
      headers.push({
        key: "Content-Security-Policy-Report-Only",
        value: buildReportOnlyCsp(process.env.NEXT_PUBLIC_API_URL),
      });
    }
    return [{ source: "/:path*", headers }];
  },
};

export default nextConfig;
