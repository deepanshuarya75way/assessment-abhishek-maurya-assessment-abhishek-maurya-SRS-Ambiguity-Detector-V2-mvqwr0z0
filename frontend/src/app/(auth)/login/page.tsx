import { AuthCard } from "@/components/auth/AuthCard";
import { privatePageMetadata } from "@/lib/seo";

export const metadata = privatePageMetadata("Log in", "Log in to the SRS Ambiguity Detector.");

export default function LoginPage() {
  return <AuthCard initialMode="login" />;
}
