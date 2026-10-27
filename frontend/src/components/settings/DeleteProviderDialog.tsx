"use client";

/**
 * Safe credential removal (contract §4.6): explicit confirmation, never a
 * one-click destroy. Mirrors the report delete dialog's contract — focus
 * lands on the safe default (Keep), Escape cancels, focus returns to the
 * trigger, and a 404 at confirm time means "already gone" (other
 * tab/device) and resolves like a success. Anything else stays open with
 * the code-mapped error so the user can retry or cancel deliberately.
 */

import { useRef, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { FormAlert } from "@/components/auth/fields";
import { ApiRequestError } from "@/lib/api";
import { isSessionGone } from "@/lib/auth";
import { deleteProvider } from "@/lib/providers";
import { providerErrorMessage } from "@/lib/provider-errors";
import type { ProviderCredential } from "@/types/providers";
import { PROVIDER_DISPLAY_NAMES } from "@/types/providers";

import { DialogShell } from "./DialogShell";

export function DeleteProviderDialog({
  credential,
  onClose,
  onDeleted,
}: {
  credential: ProviderCredential;
  onClose: () => void;
  /** Server-confirmed removal (the caller drops the row + announces). */
  onDeleted: (id: string) => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionGone, setSessionGone] = useState(false);
  const keepRef = useRef<HTMLButtonElement>(null);

  const displayName = PROVIDER_DISPLAY_NAMES[credential.provider];

  function close() {
    if (!pending) onClose();
  }

  async function handleConfirm() {
    setPending(true);
    setError(null);
    setSessionGone(false);
    try {
      await deleteProvider(credential.id);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        // Already gone (removed in another tab/device) — same outcome.
      } else {
        setPending(false);
        if (isSessionGone(err)) setSessionGone(true);
        setError(providerErrorMessage(err, "delete"));
        return;
      }
    }
    setPending(false);
    onDeleted(credential.id);
    onClose();
  }

  return (
    <DialogShell
      title={`Remove ${displayName}?`}
      description={
        <>
          <span
            className="block truncate font-medium text-ink"
            title={credential.label ?? displayName}
          >
            {credential.label ?? displayName} ·{" "}
            <code className="font-mono text-[13px]">{credential.masked_key}</code>
          </span>
          <span className="mt-1 block">
            This permanently deletes the stored credential. {displayName} stops working here
            immediately — your saved analyses are unaffected. This cannot be undone.
          </span>
        </>
      }
      dismissable={!pending}
      initialFocus={keepRef}
      onClose={close}
    >
      {error !== null ? (
        <div className="mt-4">
          <FormAlert kind="error">
            {error}{" "}
            {sessionGone ? (
              <Link
                href="/login"
                className="font-semibold text-signal underline underline-offset-2 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
              >
                Sign in again
              </Link>
            ) : null}
          </FormAlert>
        </div>
      ) : null}
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button
          ref={keepRef}
          type="button"
          onClick={close}
          disabled={pending}
          className="inline-flex items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
        >
          Keep credential
        </button>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={pending}
          className="inline-flex items-center justify-center gap-2 rounded-full bg-critic px-5 py-2 text-sm font-semibold text-white transition outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-critic/50 disabled:opacity-60"
        >
          {pending ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Removing…
            </>
          ) : (
            "Remove credential"
          )}
        </button>
      </div>
    </DialogShell>
  );
}
