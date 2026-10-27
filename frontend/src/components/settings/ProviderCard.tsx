"use client";

/**
 * One stored credential (contract §4.6): identity, state chips, masked key,
 * last-test freshness, and the five server-backed actions — test, enable /
 * disable, set-default, replace-key, remove. Every mutation renders the
 * SERVER's answer (fresh row or refetch): local state only ever tracks
 * pending flags, the latest test verdict, and transient errors. The masked
 * key renders as inert text — it is never editable, never submittable.
 */

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, FlaskConical, KeyRound, Loader2, Star, Trash2, XCircle } from "lucide-react";

import { FormAlert } from "@/components/auth/fields";
import { isSessionGone } from "@/lib/auth";
import { testProvider, updateProvider } from "@/lib/providers";
import { providerErrorMessage } from "@/lib/provider-errors";
import type { ProviderCredential, ProviderTestResult } from "@/types/providers";
import { PROVIDER_DISPLAY_NAMES } from "@/types/providers";

const SECONDARY_ACTION =
  "inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-full border border-line px-4 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60";

function formatTestDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

export function ProviderCard({
  credential,
  onChanged,
  onDefaultClaimed,
  onTested,
  onReplaceKey,
  onRemove,
}: {
  credential: ProviderCredential;
  /** Server-confirmed fresh row after enable/disable (the caller merges it). */
  onChanged: (row: ProviderCredential) => void;
  /** Default claimed (the caller refetches — the previous holder moved too). */
  onDefaultClaimed: () => void;
  /** Test verdict recorded (the caller refetches row freshness). */
  onTested: () => void;
  onReplaceKey: (credential: ProviderCredential) => void;
  onRemove: (credential: ProviderCredential) => void;
}) {
  const [testPending, setTestPending] = useState(false);
  const [verdict, setVerdict] = useState<ProviderTestResult | null>(null);
  const [togglePending, setTogglePending] = useState(false);
  const [defaultPending, setDefaultPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [sessionGone, setSessionGone] = useState(false);

  const displayName = PROVIDER_DISPLAY_NAMES[credential.provider];
  const busy = testPending || togglePending || defaultPending;

  function fail(err: unknown, context: "test" | "update") {
    if (isSessionGone(err)) setSessionGone(true);
    setActionError(providerErrorMessage(err, context));
  }

  async function handleTest() {
    if (testPending) return;
    setTestPending(true);
    setActionError(null);
    setSessionGone(false);
    try {
      const result = await testProvider(credential.id);
      setVerdict(result);
      onTested();
    } catch (err) {
      fail(err, "test");
    } finally {
      setTestPending(false);
    }
  }

  async function handleToggle() {
    if (togglePending) return;
    setTogglePending(true);
    setActionError(null);
    setSessionGone(false);
    try {
      const row = await updateProvider(credential.id, { is_enabled: !credential.is_enabled });
      onChanged(row);
    } catch (err) {
      fail(err, "update");
    } finally {
      setTogglePending(false);
    }
  }

  async function handleDefault() {
    if (defaultPending) return;
    setDefaultPending(true);
    setActionError(null);
    setSessionGone(false);
    try {
      await updateProvider(credential.id, { is_default: true });
      onDefaultClaimed();
    } catch (err) {
      fail(err, "update");
    } finally {
      setDefaultPending(false);
    }
  }

  return (
    <article
      aria-labelledby={`provider-${credential.id}-name`}
      className="rounded-card border border-line bg-paper p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3
            id={`provider-${credential.id}-name`}
            className="text-lg font-semibold tracking-[-0.01em]"
          >
            {displayName}
          </h3>
          {credential.label !== null ? (
            <p className="mt-0.5 text-sm text-ink-soft">{credential.label}</p>
          ) : null}
        </div>
        <ul aria-label={`${displayName} status`} className="flex flex-wrap gap-1.5">
          {credential.is_default ? (
            <li className="inline-flex items-center gap-1 rounded-full border border-gold/40 bg-gold-mist px-2.5 py-1 text-xs font-semibold text-ink">
              <Star className="size-3" aria-hidden />
              Default
            </li>
          ) : null}
          <li
            className={
              credential.is_enabled
                ? "inline-flex items-center gap-1.5 rounded-full bg-signal-mist px-2.5 py-1 text-xs font-semibold text-signal-deep"
                : "inline-flex items-center gap-1.5 rounded-full bg-paper-deep px-2.5 py-1 text-xs font-semibold text-ink-soft"
            }
          >
            <span
              aria-hidden
              className={
                credential.is_enabled
                  ? "size-1.5 rounded-full bg-signal"
                  : "size-1.5 rounded-full bg-ink-faint"
              }
            />
            {credential.is_enabled ? "Enabled" : "Disabled"}
          </li>
        </ul>
      </div>

      <dl className="mt-4 space-y-1.5 text-sm">
        <div className="flex flex-wrap gap-x-2">
          <dt className="text-ink-faint">Key</dt>
          <dd>
            <code className="font-mono text-[13px] text-ink">{credential.masked_key}</code>
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-2">
          <dt className="text-ink-faint">Last test</dt>
          <dd className="text-ink-soft">
            {credential.last_tested_at === null ? (
              "Never tested"
            ) : (
              <>
                {credential.last_test_status === "ok" ? "Passed" : "Failed"} ·{" "}
                {formatTestDate(credential.last_tested_at)}
              </>
            )}
          </dd>
        </div>
      </dl>

      {verdict !== null ? (
        <div
          role="status"
          className={
            verdict.ok
              ? "mt-4 flex items-start gap-2.5 rounded-xl border border-signal/40 bg-signal/10 px-4 py-3 text-sm leading-relaxed"
              : "mt-4 flex items-start gap-2.5 rounded-xl border border-gold/40 bg-gold-mist px-4 py-3 text-sm leading-relaxed"
          }
        >
          {verdict.ok ? (
            <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-signal" />
          ) : (
            <XCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-gold" />
          )}
          <div>
            {verdict.ok ? (
              <p className="font-medium">
                Connection works — {verdict.models.length}{" "}
                {verdict.models.length === 1 ? "model" : "models"} available
                {verdict.latency_ms > 0 ? ` (${verdict.latency_ms} ms)` : ""}.
              </p>
            ) : (
              <>
                <p className="font-medium">Connection test failed.</p>
                {/* Backend-curated, user-safe verdict text (contract §4.6) — the
                    one backend string rendered verbatim; capped server-side. */}
                <p className="mt-0.5 text-ink-soft">
                  {verdict.error ?? "No details were returned."}
                </p>
              </>
            )}
          </div>
        </div>
      ) : null}

      {actionError !== null ? (
        <div className="mt-4">
          <FormAlert kind="error">
            {actionError}{" "}
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

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
        <button type="button" onClick={handleTest} disabled={busy} className={SECONDARY_ACTION}>
          {testPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <FlaskConical className="size-4" aria-hidden />
          )}
          {testPending ? "Testing…" : "Test connection"}
        </button>

        <span className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-line px-3 py-2">
          <button
            type="button"
            role="switch"
            aria-checked={credential.is_enabled}
            aria-label={`${credential.is_enabled ? "Disable" : "Enable"} ${displayName}`}
            disabled={busy}
            onClick={handleToggle}
            className="group relative h-6 w-11 shrink-0 rounded-full bg-paper-deep transition outline-none focus-visible:ring-2 focus-visible:ring-signal/50 disabled:opacity-60 aria-checked:bg-signal"
          >
            <span
              aria-hidden
              className="absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform group-aria-checked:translate-x-5"
            />
          </button>
          <span aria-hidden className="text-sm font-medium text-ink-soft">
            {togglePending ? "Saving…" : credential.is_enabled ? "Enabled" : "Disabled"}
          </span>
        </span>

        {credential.is_enabled && !credential.is_default ? (
          <button
            type="button"
            onClick={handleDefault}
            disabled={busy}
            className={SECONDARY_ACTION}
          >
            {defaultPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Star className="size-4" aria-hidden />
            )}
            {defaultPending ? "Saving…" : "Set as default"}
          </button>
        ) : null}

        <button
          type="button"
          onClick={() => onReplaceKey(credential)}
          disabled={busy}
          className={SECONDARY_ACTION}
        >
          <KeyRound className="size-4" aria-hidden />
          Replace key
        </button>

        <button
          type="button"
          onClick={() => onRemove(credential)}
          disabled={busy}
          className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-full border border-critic/40 px-4 py-2 text-sm font-medium text-critic transition outline-none hover:bg-critic/10 focus-visible:ring-2 focus-visible:ring-critic/50 disabled:opacity-60"
        >
          <Trash2 className="size-4" aria-hidden />
          Remove
        </button>
      </div>

      {credential.is_default ? (
        <p className="mt-3 text-[13px] leading-relaxed text-ink-faint">
          The default provider is tried first when AI enhancement runs. Analysis works the same with
          or without one.
        </p>
      ) : null}
    </article>
  );
}
