"use client";

/**
 * Secret input for API keys — masked by default with a deliberate,
 * accessible reveal toggle. The value lives ONLY in the caller's
 * short-lived form state: never prefilled from server data (the backend
 * never sends a key back), never persisted, never logged. Callers clear
 * it on success and on close.
 */

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { TextField } from "@/components/auth/fields";

export function CredentialField({
  label,
  value,
  onChange,
  error,
  hint,
  disabled,
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div>
      <TextField
        label={label}
        name="api_key"
        type={shown ? "text" : "password"}
        autoComplete="off"
        value={value}
        onChange={onChange}
        error={error}
        hint={hint}
        maxLength={2000}
        autoFocus={autoFocus}
        disabled={disabled}
      />
      <button
        type="button"
        aria-pressed={shown}
        aria-label={shown ? "Hide API key" : "Show API key"}
        disabled={disabled}
        onClick={() => setShown((current) => !current)}
        className="mt-1.5 inline-flex items-center gap-1.5 rounded-md px-1 py-0.5 text-[13px] font-medium text-signal outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
        {shown ? "Hide" : "Show"}
      </button>
    </div>
  );
}
