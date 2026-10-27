import { Suspense } from "react";

import { AuthPanel, AuthPanelFallback } from "@/components/auth/AuthPanel";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { privatePageMetadata } from "@/lib/seo";

export const metadata = privatePageMetadata("Reset password", "Choose a new password.");

export default function ResetPasswordPage() {
  return (
    <AuthPanel>
      <Suspense fallback={<AuthPanelFallback label="Loading password reset" />}>
        <ResetPasswordForm />
      </Suspense>
    </AuthPanel>
  );
}
