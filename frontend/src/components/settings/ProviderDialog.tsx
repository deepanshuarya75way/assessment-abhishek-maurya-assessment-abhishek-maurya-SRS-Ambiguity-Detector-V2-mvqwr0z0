"use client";

/**
 * Add-provider + replace-key dialog (contract §4.6). One form shell, two
 * modes: `add` stores a first credential for a provider (select + optional
 * label + secret), `rotate` replaces a stored key (fresh secret only — the
 * masked server value is displayed as information and is NEVER placed in an
 * editable field). Client validation mirrors server shape for UX only; the
 * backend stays authoritative (`validation_error` details map onto fields).
 * The secret lives in this component's state alone: cleared on success, on
 * close, and on session loss — never persisted, never logged, never prefilled.
 */

import { useState } from "react";
import Link from "next/link";

import { FormAlert, SubmitButton, TextField } from "@/components/auth/fields";
import { ApiRequestError } from "@/lib/api";
import { isSessionGone } from "@/lib/auth";
import { createProvider, rotateProviderKey } from "@/lib/providers";
import { providerErrorMessage, providerFieldErrors } from "@/lib/provider-errors";
import type { ProviderCredential } from "@/types/providers";
import { PROVIDER_DISPLAY_NAMES, PROVIDER_IDS, isProviderId } from "@/types/providers";

import { CredentialField } from "./CredentialField";
import { DialogShell } from "./DialogShell";

const KEY_MIN_LENGTH = 4;
const KEY_MAX_LENGTH = 2000;
const LABEL_MAX_LENGTH = 80;

function keyError(value: string): string | undefined {
  if (value.length === 0) return "Enter your API key.";
  if (value.length < KEY_MIN_LENGTH || value.length > KEY_MAX_LENGTH) {
    return `API keys are between ${KEY_MIN_LENGTH} and ${KEY_MAX_LENGTH.toLocaleString()} characters.`;
  }
  return undefined;
}

export function ProviderDialog({
  mode,
  credential,
  credentials,
  onClose,
  onSaved,
}: {
  /** `add` stores a first key; `rotate` replaces the stored key. */
  mode: "add" | "rotate";
  /** The row being replaced (rotate mode). */
  credential?: ProviderCredential;
  /** Owned rows — add mode marks providers that already have an enabled key. */
  credentials: ProviderCredential[];
  onClose: () => void;
  /** Server-confirmed fresh row (the caller merges it — never local guesses). */
  onSaved: (row: ProviderCredential) => void;
}) {
  const [provider, setProvider] = useState("");
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<string, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [sessionGone, setSessionGone] = useState(false);
  const [pending, setPending] = useState(false);

  const enabledProviders = new Set(
    credentials.filter((row) => row.is_enabled).map((row) => row.provider),
  );
  const displayName =
    mode === "rotate" && credential !== undefined
      ? PROVIDER_DISPLAY_NAMES[credential.provider]
      : null;

  function close() {
    if (pending) return;
    setApiKey("");
    onClose();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    // Client mirrors of server shape (UX only — the backend re-validates).
    const errors: Partial<Record<string, string>> = {};
    if (mode === "add") {
      if (!isProviderId(provider)) errors.provider = "Choose a provider.";
      if (label.trim().length > LABEL_MAX_LENGTH) {
        errors.label = `Keep the label under ${LABEL_MAX_LENGTH} characters.`;
      }
    }
    const keyProblem = keyError(apiKey);
    if (keyProblem !== undefined) errors.api_key = keyProblem;
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setPending(true);
    setFormError(null);
    setSessionGone(false);
    try {
      let row: ProviderCredential;
      if (mode === "add") {
        if (!isProviderId(provider)) return; // unreachable: validated above
        row = await createProvider({
          provider,
          label: label.trim() === "" ? null : label.trim(),
          api_key: apiKey,
        });
      } else {
        if (credential === undefined) return; // unreachable: the parent always passes the row
        row = await rotateProviderKey(credential.id, { api_key: apiKey });
      }
      setApiKey("");
      setPending(false);
      onSaved(row);
      onClose();
    } catch (err) {
      setPending(false);
      if (isSessionGone(err)) {
        // Standard session-expiry path: drop the secret, keep the safe
        // selections (provider/label), offer the sign-in nudge inline.
        setApiKey("");
        setSessionGone(true);
        setFormError(providerErrorMessage(err, mode === "add" ? "create" : "rotate"));
        return;
      }
      if (err instanceof ApiRequestError && err.code === "validation_error") {
        const serverFields = providerFieldErrors(err);
        if (Object.keys(serverFields).length > 0) {
          setFieldErrors((current) => ({ ...current, ...serverFields }));
        }
      }
      setFormError(providerErrorMessage(err, mode === "add" ? "create" : "rotate"));
    }
  }

  return (
    <DialogShell
      title={mode === "add" ? "Add provider" : `Replace ${displayName ?? "provider"} key`}
      description={
        mode === "add" ? (
          <>
            Store one of your own API keys. We verify it with the provider before saving, then
            encrypt it before storage and never show it again — not even to you. New credentials
            start enabled; you can set a default after saving.
          </>
        ) : (
          <>
            Current key{" "}
            <code className="rounded bg-paper-deep px-1.5 py-0.5 font-mono text-[13px] text-ink">
              {credential?.masked_key}
            </code>{" "}
            (last 4 characters only). Saving replaces the stored credential immediately — enter the
            full new key below.
          </>
        )
      }
      dismissable={!pending}
      onClose={close}
    >
      <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
        {mode === "add" ? (
          <div>
            <label
              htmlFor="provider-dialog-provider"
              className="mb-1.5 block text-[13px] font-medium text-ink-soft"
            >
              Provider
            </label>
            <select
              id="provider-dialog-provider"
              name="provider"
              value={provider}
              disabled={pending}
              aria-invalid={fieldErrors.provider !== undefined ? true : undefined}
              aria-describedby={
                fieldErrors.provider !== undefined ? "provider-dialog-provider-error" : undefined
              }
              onChange={(event) => setProvider(event.target.value)}
              className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-[15px] text-ink shadow-sm outline-none transition disabled:cursor-not-allowed disabled:bg-paper-deep disabled:opacity-70 aria-[invalid=true]:border-critic aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-critic/25"
            >
              <option value="">Select a provider</option>
              {PROVIDER_IDS.map((id) => {
                const configured = enabledProviders.has(id);
                return (
                  <option key={id} value={id} disabled={configured}>
                    {PROVIDER_DISPLAY_NAMES[id]}
                    {configured ? " (already configured)" : ""}
                  </option>
                );
              })}
            </select>
            {fieldErrors.provider !== undefined ? (
              <p
                id="provider-dialog-provider-error"
                className="mt-1.5 text-[13px] font-medium leading-relaxed text-critic"
              >
                {fieldErrors.provider}
              </p>
            ) : null}
          </div>
        ) : null}

        {mode === "add" ? (
          <TextField
            label="Label (optional)"
            name="label"
            value={label}
            onChange={setLabel}
            error={fieldErrors.label}
            hint="A private nickname, like “Work”."
            maxLength={LABEL_MAX_LENGTH}
            disabled={pending}
          />
        ) : null}

        <CredentialField
          label={mode === "add" ? "API key" : "New API key"}
          value={apiKey}
          onChange={setApiKey}
          error={fieldErrors.api_key}
          hint="Masked by default. It leaves this page only inside the save request."
          disabled={pending}
        />

        {formError !== null ? (
          <FormAlert kind="error" title={sessionGone ? "Session expired" : undefined}>
            {formError}{" "}
            {sessionGone ? (
              <Link
                href="/login"
                className="font-semibold text-signal underline underline-offset-2 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
              >
                Sign in again
              </Link>
            ) : null}
          </FormAlert>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={close}
            disabled={pending}
            className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
          >
            Cancel
          </button>
          <SubmitButton
            pending={pending}
            pendingLabel={mode === "add" ? "Saving…" : "Replacing…"}
            className="w-auto"
          >
            {mode === "add" ? "Save credential" : "Replace key"}
          </SubmitButton>
        </div>
      </form>
    </DialogShell>
  );
}
