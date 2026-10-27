import type { Metadata } from "next";

import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";

import { MotionProvider } from "@/components/MotionProvider";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { SITE } from "@/lib/site";
import "./globals.css";

/* Self-hosted fonts (Fontsource) — no third-party requests, deterministic builds,
   works offline. Faces: Inter (UI/prose) + IBM Plex Mono (data/IDs). */

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  applicationName: SITE.name,
  title: { default: `${SITE.name} — ${SITE.tagline}`, template: `%s · ${SITE.name}` },
  description: SITE.description,
  icons: { icon: "/favicon.svg", apple: "/favicon.svg" },
  manifest: undefined,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <MotionProvider>
          <AuthProvider>{children}</AuthProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
