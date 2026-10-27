import { SettingsScreen } from "@/components/settings/SettingsScreen";
import { privatePageMetadata } from "@/lib/seo";

/** Private product surface — never indexed (the project contract). */
export const metadata = privatePageMetadata("Settings", "Private account and provider settings.");

export default function SettingsPage() {
  return <SettingsScreen />;
}
