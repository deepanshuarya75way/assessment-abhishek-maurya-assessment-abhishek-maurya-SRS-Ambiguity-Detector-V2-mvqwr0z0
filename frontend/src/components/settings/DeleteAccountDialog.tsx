"use client";

/**
 * DELETE-typed account deletion (contract §4.2: `{confirmation: "DELETE"}` →
 * 204). The typed word is the point: no one-click destroy, no pre-armed
 * confirm. Mirrors the delete dialog contract — focus lands on the safe
 * default (Keep), Escape cancels, focus returns to the trigger, the dialog
 * stays open with a code-mapped error on failure. A 401 mid-delete is
 * reported HONESTLY (session ended; sign back in if the account still
 * exists) rather than guessed as success or failure.
 */

import { useRef, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { FormAlert, TextField } from "@/components/auth/fields";
import { deleteAccount, isSessionGone } from "@/lib/auth";
import { authErrorMessage } from "@/lib/auth-errors";

import { DialogShell } from "./DialogShell";

export function DeleteAccountDialog({
  email,
  onClose,
  onDeleted,
}: {
  /** Shown so the user can verify WHICH account is about to go. */
  email: string;
  onClose: () => void;
  /** Server-confirmed 204 (the caller clears auth + renders the farewell). */
  onDeleted: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionGone, setSessionGone] = useState(false);
  const keepRef = useRef<HTMLButtonElement>(null);

  const armed = confirmation === "DELETE";

  function close() {
    if (!pending) onClose();
  }

  async function handleConfirm() {
    if (!armed) return;
    setPending(true);
    setError(null);
    setSessionGone(false);
    try {
      await deleteAccount();
    } catch (err) {
      setPending(false);
      if (isSessionGone(err)) setSessionGone(true);
      setError(authErrorMessage(err, "session"));
      return;
    }
    setPending(false);
    onDeleted();
    onClose();
  }

  return (
    <DialogShell
      title="Delete your account?"
      description={
        <>
          <span className="block truncate font-medium text-ink" title={email}>
            {email}
          </span>
          <span className="mt-1 block">
            This permanently deletes your account, analyses, uploaded documents, and saved AI
            provider keys, and signs you out everywhere. This cannot be undone.
          </span>
        </>
      }
      dismissable={!pending}
      initialFocus={keepRef}
      onClose={close}
    >
      <div className="mt-4">
        <TextField
          label="Type DELETE to confirm"
          name="confirmation"
          autoComplete="off"
          value={confirmation}
          disabled={pending}
          onChange={(value) => setConfirmation(value)}
          hint="Capital letters, exactly as shown."
        />
      </div>
      {error !== null ? (
        <div className="mt-4">
          <FormAlert kind="error">
            {sessionGone ? (
              <>
                Your session ended before this finished — if the account still exists,{" "}
                <Link
                  href="/login"
                  className="font-semibold text-signal underline underline-offset-2 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
                >
                  sign in
                </Link>{" "}
                and try again.
              </>
            ) : (
              error
            )}
          </FormAlert>
        </div>
      ) : null}
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button
          ref={keepRef}
          type="button"
          onClick={close}
          disabled={pending}
          className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60"
        >
          Keep my account
        </button>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={pending || !armed}
          className="inline-flex items-center justify-center gap-2 rounded-full bg-critic px-5 py-2 text-sm font-semibold text-white transition outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-critic/50 disabled:opacity-60"
        >
          {pending ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Deleting…
            </>
          ) : (
            "Delete account"
          )}
        </button>
      </div>
    </DialogShell>
  );
}
