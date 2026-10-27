"use client";

/** Registration form. A successful account creation starts a session and calls `onSuccess`. */

import { useId, useState } from "react";

import { useAuth } from "@/hooks/useAuth";
import { authErrorMessage, validationFieldErrors } from "@/lib/auth-errors";
import {
  collapseName,
  normalizeEmail,
  validateConfirmPassword,
  validateEmail,
  validateName,
  validatePassword,
} from "@/lib/auth-validation";

import { FormAlert, PasswordField, PasswordRequirements, SubmitButton, TextField } from "./fields";

interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
  confirm?: string;
}

export function SignupForm({ onSuccess }: { onSuccess: (email: string) => void }) {
  const { signup } = useAuth();
  const requirementsId = useId();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);


  function clearFieldError(field: keyof FieldErrors) {
    setFieldErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;

    const errors: FieldErrors = {};
    const nameError = validateName(name);
    if (nameError) errors.name = nameError;
    const emailError = validateEmail(email);
    if (emailError) errors.email = emailError;
    const passwordError = validatePassword(password, email);
    if (passwordError) errors.password = passwordError;
    const confirmError = validateConfirmPassword(password, confirm);
    if (confirmError) errors.confirm = confirmError;
    setFieldErrors(errors);
    setFormError(null);
    if (errors.name ?? errors.email ?? errors.password ?? errors.confirm) return;

    setPending(true);
    try {
      const normalizedEmail = normalizeEmail(email);
      await signup({
        name: collapseName(name),
        email: normalizedEmail,
        password,
      });
      onSuccess(normalizedEmail);
    } catch (err) {
      const serverFields = validationFieldErrors(err);
      setFieldErrors((prev) => ({
        ...prev,
        name: serverFields.name ?? prev.name,
        email: serverFields.email ?? prev.email,
        password: serverFields.password ?? prev.password,
      }));
      setFormError(authErrorMessage(err, "register"));
    } finally {
      setPending(false);
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-label="Create account">
      <fieldset disabled={pending} className="m-0 space-y-4 border-0 p-0">
        {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}
        <TextField
          label="Name"
          name="name"
          autoComplete="name"
          maxLength={100}
          placeholder="Ada Lovelace"
          value={name}
          onChange={(value) => {
            setName(value);
            clearFieldError("name");
          }}
          error={fieldErrors.name}
        />
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
            clearFieldError("email");
          }}
          error={fieldErrors.email}
        />
        <div>
          <PasswordField
            label="Password"
            name="password"
            autoComplete="new-password"
            describedById={requirementsId}
            value={password}
            onChange={(value) => {
              setPassword(value);
              clearFieldError("password");
            }}
            error={fieldErrors.password}
          />
          <PasswordRequirements id={requirementsId} />
        </div>
        <PasswordField
          label="Confirm password"
          name="confirm"
          autoComplete="new-password"
          value={confirm}
          onChange={(value) => {
            setConfirm(value);
            clearFieldError("confirm");
          }}
          error={fieldErrors.confirm}
        />
        <SubmitButton pending={pending} pendingLabel="Creating account…">
          Create account
        </SubmitButton>
      </fieldset>
    </form>
  );
}
