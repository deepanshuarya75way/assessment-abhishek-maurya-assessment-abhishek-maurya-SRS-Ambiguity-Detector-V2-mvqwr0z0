import { AnalyzerWorkspace } from "@/components/analyzer/AnalyzerWorkspace";
import { privatePageMetadata } from "@/lib/seo";

/** Private product surface — never indexed (the project contract). */
export const metadata = privatePageMetadata("Analyzer", "Analyze private SRS text or uploads.");

export default function AnalyzerPage() {
  return <AnalyzerWorkspace />;
}
