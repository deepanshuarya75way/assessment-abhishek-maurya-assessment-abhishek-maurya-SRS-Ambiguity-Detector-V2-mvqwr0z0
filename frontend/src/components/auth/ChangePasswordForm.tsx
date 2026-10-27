"use client";

/**
 * Signed-in password change (current + new). Fully built and tested in Stage 05
 * but NOT mounted on any page yet — the settings/profile host arrives in a
 * later stage, which will import this component as-is.
 */

import { useId, useState } from "react";

import { ApiRequestError } from "@/lib/api";
import { changePassword } from "@/lib/auth";
import { authErrorMessage, validationFieldErrors } from "@/lib/auth-errors";
import {
  validateConfirmPassword,
  validateCurrentPassword,
  validatePassword,
} from "@/lib/auth-validation";

import { FormAlert, PasswordField, PasswordRequirements, SubmitButton } from "./fields";

export function ChangePasswordForm() {
  const requirementsId = useId();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [currentError, setCurrentError] = useState<string | undefined>(undefined);
  const [passwordError, setPasswordError] = useState<string | undefined>(undefined);
  const [confirmError, setConfirmError] = useState<string | undefined>(undefined);
  const [formError, setFormError] = useState<string | null>(null);
  const [updated, setUpdated] = useState(false);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const curError = validateCurrentPassword(current);
    const pwError = validatePassword(password);
    const cfError = validateConfirmPassword(password, confirm);
    setCurrentError(curError ?? undefined);
    setPasswordError(pwError ?? undefined);
    setConfirmError(cfError ?? undefined);
    setFormError(null);
    setUpdated(false);
    if (curError ?? pwError ?? cfError) return;

    setPending(true);
    try {
      await changePassword({ current_password: current, new_password: password });
      setCurrent("");
      setPassword("");
      setConfirm("");
      setUpdated(true);
    } catch (err) {
      const serverFields = validationFieldErrors(err);
      const message = authErrorMessage(err, "change");
      // Field-shaped failures land on the field; everything else goes form-level.
      if (err instanceof ApiRequestError && err.code === "current_password_incorrect") {
        setCurrentError(message);
      } else if (serverFields.new_password ?? serverFields.password) {
        setPasswordError(serverFields.new_password ?? serverFields.password);
        setFormError(message);
      } else {
        setFormError(message);
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-label="Change password">
      <fieldset disabled={pending} className="m-0 space-y-4 border-0 p-0">
        {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}
        {updated ? <FormAlert kind="success">Password updated.</FormAlert> : null}
        <PasswordField
          label="Current password"
          name="current_password"
          autoComplete="current-password"
          value={current}
          onChange={(value) => {
            setCurrent(value);
            setCurrentError(undefined);
          }}
          error={currentError}
        />
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
  );
}
