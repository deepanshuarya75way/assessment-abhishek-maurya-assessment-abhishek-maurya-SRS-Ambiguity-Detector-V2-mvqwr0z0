import { AuthCard } from "@/components/auth/AuthCard";
import { privatePageMetadata } from "@/lib/seo";

export const metadata = privatePageMetadata(
  "Sign up",
  "Create your SRS Ambiguity Detector account.",
);

export default function SignupPage() {
  return <AuthCard initialMode="signup" />;
}
