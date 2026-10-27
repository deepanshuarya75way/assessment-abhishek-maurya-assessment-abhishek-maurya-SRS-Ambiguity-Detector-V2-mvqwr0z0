"use client";

/**
 * Password-reset request. The backend always answers 202 (anti-enumeration),
 * so success copy is unconditional AND non-committal: identical for unknown
 * addresses, never claiming an email was delivered.
 */

import Link from "next/link";
import { useState } from "react";

import { requestPasswordReset } from "@/lib/auth";
import { authErrorMessage } from "@/lib/auth-errors";
import { normalizeEmail, validateEmail } from "@/lib/auth-validation";

import { FormAlert, SubmitButton, TextField } from "./fields";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | undefined>(undefined);
  const [formError, setFormError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const [pending, setPending] = useState(false);


  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const error = validateEmail(email);
    setEmailError(error ?? undefined);
    setFormError(null);
    if (error) return;

    setPending(true);
    try {
      await requestPasswordReset({
        email: normalizeEmail(email),
      });
      setRequested(true);
    } catch (err) {
      setFormError(authErrorMessage(err, "forgot"));
    } finally {
      setPending(false);
    }
  }

  if (requested) {
    return (
      <div className="py-4">
        <h1 className="text-[26px] font-semibold tracking-tight text-ink">Check your inbox</h1>
        <div className="mt-4">
          <FormAlert kind="success">
            If an account exists for this email, a reset link is on its way — it expires in 60
            minutes.
          </FormAlert>
        </div>
        <button
          type="button"
          onClick={() => setRequested(false)}
          className="mt-6 w-full rounded-xl border border-line bg-white px-4 py-2.5 text-[14px] font-semibold text-ink outline-none transition hover:border-ink-faint hover:bg-paper focus-visible:ring-2 focus-visible:ring-signal/40"
        >
          Use a different email
        </button>
        <p className="mt-4 text-center text-[14px] text-ink-soft">
          <Link
            href="/login"
            className="rounded-md font-medium text-signal outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
          >
            Back to log in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="py-4">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">Reset your password</h1>
      <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
        Enter the email you signed up with and we&apos;ll send you a reset link.
      </p>
      <form noValidate onSubmit={handleSubmit} aria-label="Request password reset" className="mt-6">
        <fieldset disabled={pending} className="m-0 space-y-4 border-0 p-0">
          {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            maxLength={320}
            placeholder="you@example.com"
            value={email}
            onChange={(value) => {
              setEmail(value);
              setEmailError(undefined);
            }}
            error={emailError}
          />
            <SubmitButton pending={pending} pendingLabel="Sending…">
            Send reset link
          </SubmitButton>
        </fieldset>
      </form>
      <p className="mt-6 text-center text-[14px] text-ink-soft">
        Remembered it?{" "}
        <Link
          href="/login"
          className="rounded-md font-medium text-signal outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
        >
          Back to log in
        </Link>
      </p>
    </div>
  );
}
