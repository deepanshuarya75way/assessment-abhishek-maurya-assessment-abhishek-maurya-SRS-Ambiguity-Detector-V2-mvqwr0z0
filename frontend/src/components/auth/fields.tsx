"use client";

/**
 * Shared auth form primitives — one visual language for every auth form.
 * Full keyboard + screen-reader support: every control is labelled, errors are
 * wired via `aria-describedby`, and form-level failures use alert/status roles.
 */

import { useId, useState } from "react";
import { AlertTriangle, CheckCircle2, Eye, EyeOff, Info, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

const INPUT_CLASSES =
  "w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-[15px] text-ink shadow-sm outline-none transition placeholder:text-ink-faint disabled:cursor-not-allowed disabled:bg-paper-deep disabled:opacity-70";

export interface TextFieldProps {
  label: string;
  name: string;
  type?: "text" | "email" | "password";
  autoComplete?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  hintId?: string;
  placeholder?: string;
  maxLength?: number;
  inputMode?: "email" | "text";
  autoFocus?: boolean;
  disabled?: boolean;
}

export function TextField({
  label,
  name,
  type = "text",
  autoComplete,
  value,
  onChange,
  error,
  hint,
  hintId,
  placeholder,
  maxLength,
  inputMode,
  autoFocus,
  disabled,
}: TextFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const describedBy =
    [error ? errorId : null, hintId ?? null].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium text-ink-soft">
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        autoComplete={autoComplete}
        value={value}
        maxLength={maxLength}
        inputMode={inputMode}
        autoFocus={autoFocus}
        disabled={disabled}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          INPUT_CLASSES,
          error
            ? "border-critic focus:border-critic focus:ring-2 focus:ring-critic/25"
            : "focus:border-signal focus:ring-2 focus:ring-signal/25",
        )}
      />
      {hint ? <p className="mt-1.5 text-[13px] leading-relaxed text-ink-faint">{hint}</p> : null}
      {error ? (
        <p id={errorId} className="mt-1.5 text-[13px] font-medium leading-relaxed text-critic">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface PasswordFieldProps extends Omit<TextFieldProps, "type"> {
  describedById?: string;
}

export function PasswordField({ describedById, ...props }: PasswordFieldProps) {
  const [shown, setShown] = useState(false);
  return (
    <div>
      <TextField
        {...props}
        type={shown ? "text" : "password"}
        hintId={describedById ?? props.hintId}
      />
      <button
        type="button"
        aria-pressed={shown}
        aria-label={shown ? "Hide password" : "Show password"}
        disabled={props.disabled}
        onClick={() => setShown((value) => !value)}
        className="mt-1.5 inline-flex items-center gap-1.5 rounded-md px-1 py-0.5 text-[13px] font-medium text-signal outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
        {shown ? "Hide" : "Show"}
      </button>
    </div>
  );
}

export interface FormAlertProps {
  kind: "error" | "success" | "info";
  title?: string;
  children: React.ReactNode;
}

export function FormAlert({ kind, title, children }: FormAlertProps) {
  const Icon = kind === "error" ? AlertTriangle : kind === "success" ? CheckCircle2 : Info;
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-4 py-3 text-[14px] leading-relaxed text-ink",
        kind === "error" && "border-critic/35 bg-critic/10",
        kind === "success" && "border-sev-low/40 bg-sev-low/10",
        kind === "info" && "border-signal/40 bg-signal/10",
      )}
    >
      <Icon
        aria-hidden
        className={cn(
          "mt-0.5 size-4 shrink-0",
          kind === "error" && "text-critic",
          kind === "success" && "text-sev-low",
          kind === "info" && "text-signal",
        )}
      />
      <div>
        {title ? <p className="font-semibold">{title}</p> : null}
        <div className={title ? "mt-0.5" : undefined}>{children}</div>
      </div>
    </div>
  );
}

export interface SubmitButtonProps {
  pending: boolean;
  pendingLabel: string;
  /** Extra disable reason (e.g. resend cooldown) — announced via adjacent text. */
  disabled?: boolean;
  /** Layout override (e.g. `w-auto` for dialog action rows — default is full-width). */
  className?: string;
  children: React.ReactNode;
}

export function SubmitButton({
  pending,
  pendingLabel,
  disabled,
  className,
  children,
}: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className={cn("btn-primary w-full justify-center", className)}
    >
      {pending ? (
        <>
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {pendingLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
}

/** Static password policy checklist (server enforces; shown so failures never surprise). */
const PASSWORD_REQUIREMENTS = [
  "At least 12 characters",
  "Not a commonly used password",
  "Doesn't contain your email address",
] as const;

export function PasswordRequirements({ id }: { id: string }) {
  return (
    <ul id={id} aria-label="Password requirements" className="mt-2 space-y-1">
      {PASSWORD_REQUIREMENTS.map((requirement) => (
        <li
          key={requirement}
          className="flex items-start gap-2 text-[13px] leading-relaxed text-ink-faint"
        >
          <span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-signal" />
          {requirement}
        </li>
      ))}
    </ul>
  );
}
