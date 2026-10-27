import { AuthPanel } from "@/components/auth/AuthPanel";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { privatePageMetadata } from "@/lib/seo";

export const metadata = privatePageMetadata("Forgot password", "Request a password reset link.");

export default function ForgotPasswordPage() {
  return (
    <AuthPanel>
      <ForgotPasswordForm />
    </AuthPanel>
  );
}
