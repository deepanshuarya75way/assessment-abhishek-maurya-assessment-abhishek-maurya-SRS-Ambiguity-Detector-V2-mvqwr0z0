"use client";

/**
 * Log-in form — credentials collection + API call. Navigation stays with the
 * host (via `onSuccess`) so this form is usable anywhere and testable without
 * a router. Unverified accounts CAN log in (backend gates per-endpoint).
 */

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/hooks/useAuth";
import { authErrorMessage, validationFieldErrors } from "@/lib/auth-errors";
import { normalizeEmail, validateEmail } from "@/lib/auth-validation";

import { FormAlert, PasswordField, SubmitButton, TextField } from "./fields";

interface FieldErrors {
  email?: string;
  password?: string;
}

export function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);


  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;

    const errors: FieldErrors = {};
    const emailError = validateEmail(email);
    if (emailError) errors.email = emailError;
    if (!password) errors.password = "Enter your password.";
    setFieldErrors(errors);
    setFormError(null);
    if (errors.email ?? errors.password) return;

    setPending(true);
    try {
      await login({
        email: normalizeEmail(email),
        password,
      });
      onSuccess();
    } catch (err) {
      const serverFields = validationFieldErrors(err);
      setFieldErrors({
        email: serverFields.email,
        password: serverFields.password ?? serverFields.current_password,
      });
      setFormError(authErrorMessage(err, "login"));
    } finally {
      setPending(false);
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-label="Log in">
      <fieldset disabled={pending} className="m-0 space-y-4 border-0 p-0">
        {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}
        <TextField
          label="Email"
          name="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          maxLength={320}
          placeholder="you@example.com"
          value={email}
          onChange={(value) => {
            setEmail(value);
            if (fieldErrors.email) setFieldErrors((prev) => ({ ...prev, email: undefined }));
          }}
          error={fieldErrors.email}
        />
        <div>
          <PasswordField
            label="Password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(value) => {
              setPassword(value);
              if (fieldErrors.password) {
                setFieldErrors((prev) => ({ ...prev, password: undefined }));
              }
            }}
            error={fieldErrors.password}
          />
          <p className="mt-1 text-right">
            <Link
              href="/forgot-password"
              className="rounded-md text-[13px] font-medium text-signal outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
            >
              Forgot password?
            </Link>
          </p>
        </div>
        <SubmitButton pending={pending} pendingLabel="Logging in…">
          Log in
        </SubmitButton>
      </fieldset>
    </form>
  );
}
