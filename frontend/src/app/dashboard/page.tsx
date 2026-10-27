import { DashboardScreen } from "@/components/dashboard/DashboardScreen";
import { privatePageMetadata } from "@/lib/seo";

/** Private product surface — never indexed (the project contract). */
export const metadata = privatePageMetadata("Dashboard", "Private analysis quality dashboard.");

export default function DashboardPage() {
  return <DashboardScreen />;
}
