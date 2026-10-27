import { AnalysisReportScreen } from "@/components/analyzer/AnalysisReportScreen";
import { privatePageMetadata } from "@/lib/seo";

/** Private report route — never indexed and never user-title canonicalized. */
export const metadata = privatePageMetadata("Analysis result", "Private saved analysis report.");

export default function AnalysisDetailPage() {
  return <AnalysisReportScreen />;
}
