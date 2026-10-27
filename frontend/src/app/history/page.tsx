import { HistoryScreen } from "@/components/history/HistoryScreen";
import { privatePageMetadata } from "@/lib/seo";

/** Private product surface — never indexed (the project contract). */
export const metadata = privatePageMetadata("History", "Private analysis history.");

export default function HistoryPage() {
  return <HistoryScreen />;
}
