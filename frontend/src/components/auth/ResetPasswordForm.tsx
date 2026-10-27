"use client";

/**
 * Password reset via emailed `?token=` link. The token is never displayed or
 * logged. Success does NOT log in (the backend sets no cookies here — reset is
 * logout-everywhere), so the panel guides to the login page.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { useId, useState } from "react";

import { resetPassword } from "@/lib/auth";
import { authErrorMessage, validationFieldErrors } from "@/lib/auth-errors";
import { validateConfirmPassword, validatePassword, validateToken } from "@/lib/auth-validation";

import { FormAlert, PasswordField, PasswordRequirements, SubmitButton } from "./fields";

export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requirementsId = useId();
  const token = searchParams.get("token");
  const linkToken = token !== null && !validateToken(token) ? token : null;
  const linkValid = linkToken !== null;

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [passwordError, setPasswordError] = useState<string | undefined>(undefined);
  const [confirmError, setConfirmError] = useState<string | undefined>(undefined);
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);


  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || linkToken === null) return;
    const pwError = validatePassword(password);
    const cfError = validateConfirmPassword(password, confirm);
    setPasswordError(pwError ?? undefined);
    setConfirmError(cfError ?? undefined);
    setFormError(null);
    if (pwError ?? cfError) return;

    setPending(true);
    try {
      await resetPassword({
        token: linkToken,
        new_password: password,
      });
      setDone(true);
    } catch (err) {
      const serverFields = validationFieldErrors(err);
      if (serverFields.new_password ?? serverFields.password) {
        setPasswordError(serverFields.new_password ?? serverFields.password);
      }
      setFormError(authErrorMessage(err, "reset"));
    } finally {
      setPending(false);
    }
  }

  if (!linkValid) {
    return (
      <div className="py-4">
        <h1 className="text-[26px] font-semibold tracking-tight text-ink">Invalid reset link</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
          This link is incomplete or malformed. Reset links also expire after 60 minutes — request a
          fresh one.
        </p>
        <Link href="/forgot-password" className="btn-primary mt-6 w-full justify-center">
          Request a new link
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="py-4">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-sev-low/10">
          <CheckCircle2 className="size-6 text-sev-low" aria-hidden />
        </div>
        <h1 className="mt-5 text-[26px] font-semibold tracking-tight text-ink">Password updated</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
          Your password is changed and every other session is signed out. Log in with the new one.
        </p>
        <button
          type="button"
          onClick={() => router.replace("/login")}
          className="btn-primary mt-6 w-full justify-center"
        >
          Back to log in
        </button>
      </div>
    );
  }

  return (
    <div className="py-4">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">Choose a new password</h1>
      <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
        Pick something long and unique — you&apos;ll use it to log in everywhere.
      </p>
      <form noValidate onSubmit={handleSubmit} aria-label="Reset password" className="mt-6">
        <fieldset disabled={pending} className="m-0 space-y-4 border-0 p-0">
          {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}
          <div>
            <PasswordField
              label="New password"
              name="new_password"
              autoComplete="new-password"
              describedById={requirementsId}
              value={password}
              onChange={(value) => {
                setPassword(value);
                setPasswordError(undefined);
              }}
              error={passwordError}
            />
            <PasswordRequirements id={requirementsId} />
          </div>
          <PasswordField
            label="Confirm new password"
            name="confirm"
            autoComplete="new-password"
            value={confirm}
            onChange={(value) => {
              setConfirm(value);
              setConfirmError(undefined);
            }}
            error={confirmError}
          />
            <SubmitButton pending={pending} pendingLabel="Updating…">
            Update password
          </SubmitButton>
        </fieldset>
      </form>
    </div>
  );
}
