"use client";

/**
 * Settings (Stage 13 providers + Stage 16 account sections): profile, password,
 * AI provider credentials (list, add, test, enable/disable, default,
 * replace-key, remove), privacy notes, and DELETE-typed account deletion.
 * Provider states mirror dashboard/history: loading skeleton, session-gone
 * sign-in nudge, code-mapped error + retry, deliberate first-use panel, and
 * wrong-shape rejection. The backend is the source of truth after EVERY
 * mutation: each success ends in a silent re-read (server ordering, server
 * flags — no optimistic merges), with a visible confirmation and a spoken
 * status announcement. Secrets never appear here: dialogs own the short-lived
 * keystrokes and this screen only ever sees masked metadata. After a confirmed
 * account deletion the protected tree unmounts into a farewell panel (the
 * session is dead, so no redirect could carry the confirmation anywhere).
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Inbox, KeyRound, Plus, TriangleAlert } from "lucide-react";

import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { Container } from "@/components/layout/Container";
import { Reveal } from "@/components/Reveal";
import { useAuth } from "@/hooks/useAuth";
import { isSessionGone } from "@/lib/auth";
import { listProviders } from "@/lib/providers";
import { providerErrorMessage } from "@/lib/provider-errors";
import type { ProviderCredential } from "@/types/providers";
import { PROVIDER_DISPLAY_NAMES, isProviderId } from "@/types/providers";

import { DeleteAccountDialog } from "./DeleteAccountDialog";
import { DeleteProviderDialog } from "./DeleteProviderDialog";
import { PrivacySection } from "./PrivacySection";
import { ProfileSection } from "./ProfileSection";
import { ProviderCard } from "./ProviderCard";
import { ProviderDialog } from "./ProviderDialog";

const UNEXPECTED_RESPONSE = "The service returned an unexpected response.";

type LoadState =
  | { status: "loading" }
  | { status: "session-gone" }
  | { status: "load-failed"; message: string }
  | { status: "ready"; rows: ProviderCredential[] };

type DialogState =
  | { open: false }
  | { open: true; mode: "add" }
  | { open: true; mode: "rotate"; credential: ProviderCredential }
  | { open: true; mode: "delete"; credential: ProviderCredential };

function isCredentialArray(data: unknown): data is ProviderCredential[] {
  if (!Array.isArray(data)) return false;
  return data.every((row) => {
    if (typeof row !== "object" || row === null) return false;
    const candidate = row as Record<string, unknown>;
    return (
      typeof candidate.id === "string" &&
      isProviderId(candidate.provider) &&
      (candidate.label === null || typeof candidate.label === "string") &&
      typeof candidate.masked_key === "string" &&
      typeof candidate.is_enabled === "boolean" &&
      typeof candidate.is_default === "boolean" &&
      (candidate.last_tested_at === null || typeof candidate.last_tested_at === "string") &&
      (candidate.last_test_status === null ||
        candidate.last_test_status === "ok" ||
        candidate.last_test_status === "failed")
    );
  });
}

function BackLink() {
  return (
    <Link
      href="/dashboard"
      className="inline-flex items-center gap-1.5 rounded-full font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
    >
      <ArrowLeft className="size-3.5" aria-hidden />
      Dashboard
    </Link>
  );
}

function SettingsContent({ onDeleted }: { onDeleted: () => void }) {
  const { user, clearAuth } = useAuth();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [refreshKey, setRefreshKey] = useState(0);
  const [dialog, setDialog] = useState<DialogState>({ open: false });
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listProviders().then(
      (data) => {
        if (cancelled) return;
        if (!isCredentialArray(data)) {
          setState({ status: "load-failed", message: UNEXPECTED_RESPONSE });
          return;
        }
        setState({ status: "ready", rows: data });
      },
      (err: unknown) => {
        if (cancelled) return;
        if (isSessionGone(err)) setState({ status: "session-gone" });
        else setState({ status: "load-failed", message: providerErrorMessage(err, "load") });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  /**
   * Silent re-read after a mutation: the current rows stay rendered (no
   * skeleton flash); only the settled server list replaces them. A failed
   * refresh keeps the stale rows behind an honest notice — never a lie.
   */
  const refreshList = useCallback(async (announcement: string | null) => {
    try {
      const data = await listProviders();
      if (!isCredentialArray(data)) {
        setNotice("Saved, but the list couldn't be refreshed — please reload the page.");
        return;
      }
      setState({ status: "ready", rows: data });
      if (announcement !== null) setNotice(announcement);
    } catch (err) {
      if (isSessionGone(err)) {
        setState({ status: "session-gone" });
        return;
      }
      setNotice("Saved, but the list couldn't be refreshed — please try again.");
    }
  }, []);

  function retryLoad() {
    setState({ status: "loading" });
    setRefreshKey((count) => count + 1);
  }

  const rows = state.status === "ready" ? state.rows : null;

  return (
    <Container className="max-w-3xl py-10 sm:py-14">
      <BackLink />
      <Reveal>
        <p className="mt-4 font-mono text-xs tracking-[0.2em] text-signal uppercase">Settings</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.02em] text-balance sm:text-4xl">
          Settings
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-soft">
          Account, security, and data controls. Analysis runs deterministically and needs nothing
          here — AI providers below are optional enhancements.
        </p>
      </Reveal>

      <ProfileSection />

      <section aria-labelledby="password-heading" className="mt-10">
        <h2 id="password-heading" className="text-2xl font-semibold tracking-[-0.02em]">
          Password
        </h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
          Changing your password signs you out everywhere else. If you signed up with an email and
          password, you can also reset it from the login page.
        </p>
        <div className="mt-6 max-w-xl">
          <ChangePasswordForm />
        </div>
      </section>

      {state.status === "loading" ? (
        <div
          aria-busy="true"
          aria-label="Loading settings"
          className="mt-8 rounded-card border border-line bg-paper p-8"
        >
          <div className="animate-pulse space-y-3">
            <div className="h-6 w-48 rounded-lg bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-full rounded bg-paper-deep" />
            <div className="h-4 w-2/3 rounded bg-paper-deep" />
          </div>
        </div>
      ) : null}

      {state.status === "session-gone" ? (
        <div role="status" className="mt-8 max-w-xl">
          <h2 className="text-2xl font-semibold tracking-[-0.02em]">Session expired</h2>
          <p className="mt-3 text-base leading-relaxed text-ink-soft">
            Sign in again to manage your settings.
          </p>
          <p className="mt-5">
            <Link
              href="/login"
              className="inline-flex items-center justify-center rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Sign in
            </Link>
          </p>
        </div>
      ) : null}

      {state.status === "load-failed" ? (
        <div
          role="alert"
          className="mt-8 flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
        >
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-gold" aria-hidden />
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.01em]">
              Couldn&apos;t load your settings
            </h2>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">{state.message}</p>
            <button
              type="button"
              onClick={retryLoad}
              className="mt-4 inline-flex items-center justify-center rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Retry
            </button>
          </div>
        </div>
      ) : null}

      {rows !== null ? (
        <section aria-labelledby="ai-providers-heading" className="mt-10">
          <Reveal>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 id="ai-providers-heading" className="text-2xl font-semibold tracking-[-0.02em]">
                  AI providers
                </h2>
                <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
                  Optional. Your own API keys, encrypted at rest and never shown again after saving
                  — each credential stays private to your account.
                </p>
              </div>
              {rows.length > 0 ? (
                <button
                  type="button"
                  onClick={() => {
                    setNotice(null);
                    setDialog({ open: true, mode: "add" });
                  }}
                  className="inline-flex items-center justify-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
                >
                  <Plus className="size-4" aria-hidden />
                  Add provider
                </button>
              ) : null}
            </div>
          </Reveal>

          {notice !== null ? (
            <div
              role="status"
              className="mt-6 flex items-start gap-3 rounded-card border border-line bg-paper p-5"
            >
              <KeyRound className="mt-0.5 size-5 shrink-0 text-signal" aria-hidden />
              <div className="flex-1">
                <p className="text-[15px] leading-relaxed">{notice}</p>
              </div>
              <button
                type="button"
                onClick={() => setNotice(null)}
                aria-label="Dismiss notification"
                className="rounded-full px-2 py-1 font-mono text-xs font-medium text-ink-soft transition outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/50"
              >
                Dismiss
              </button>
            </div>
          ) : null}

          {rows.length === 0 ? (
            <div
              role="status"
              className="mt-6 flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
            >
              <Inbox className="mt-0.5 size-5 shrink-0 text-ink-faint" aria-hidden />
              <div>
                <h3 className="text-lg font-semibold tracking-[-0.01em]">No AI providers yet</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
                  Nothing to do here unless you want AI enhancement later: ambiguity detection,
                  scoring, history, and the dashboard all work without any provider. If you add one,
                  you supply your own API key — it is encrypted before storage and never displayed
                  again.
                </p>
                <p className="mt-4">
                  <button
                    type="button"
                    onClick={() => {
                      setNotice(null);
                      setDialog({ open: true, mode: "add" });
                    }}
                    className="inline-flex items-center justify-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
                  >
                    Add your first provider
                  </button>
                </p>
              </div>
            </div>
          ) : (
            <ul className="mt-6 space-y-4">
              {rows.map((row) => (
                <li key={row.id}>
                  <ProviderCard
                    credential={row}
                    onChanged={(fresh) =>
                      refreshList(
                        `${PROVIDER_DISPLAY_NAMES[fresh.provider]} ${fresh.is_enabled ? "enabled" : "disabled"}.`,
                      )
                    }
                    onDefaultClaimed={() =>
                      refreshList(
                        `${PROVIDER_DISPLAY_NAMES[row.provider]} is now the default provider.`,
                      )
                    }
                    onTested={() => refreshList(null)}
                    onReplaceKey={(target) => {
                      setNotice(null);
                      setDialog({ open: true, mode: "rotate", credential: target });
                    }}
                    onRemove={(target) => {
                      setNotice(null);
                      setDialog({ open: true, mode: "delete", credential: target });
                    }}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      <PrivacySection />

      <section aria-labelledby="delete-account-heading" className="mt-10">
        <h2 id="delete-account-heading" className="text-2xl font-semibold tracking-[-0.02em]">
          Delete account
        </h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
          Permanently removes your account, analyses, uploaded documents, and saved AI provider
          keys, and signs you out everywhere. You will type DELETE to confirm — this cannot be
          undone.
        </p>
        <p className="mt-4">
          <button
            type="button"
            onClick={() => setDeleteAccountOpen(true)}
            className="inline-flex items-center justify-center rounded-full border border-critic/50 px-5 py-2.5 text-[15px] font-semibold text-critic transition outline-none hover:bg-critic hover:text-white focus-visible:ring-2 focus-visible:ring-critic/50"
          >
            Delete my account…
          </button>
        </p>
      </section>

      {deleteAccountOpen ? (
        <DeleteAccountDialog
          email={user?.email ?? ""}
          onClose={() => setDeleteAccountOpen(false)}
          onDeleted={() => {
            clearAuth();
            onDeleted();
          }}
        />
      ) : null}

      {dialog.open && dialog.mode === "add" ? (
        <ProviderDialog
          mode="add"
          credentials={rows ?? []}
          onClose={() => setDialog({ open: false })}
          onSaved={(row) =>
            refreshList(
              `${PROVIDER_DISPLAY_NAMES[row.provider]} credential saved. The key is stored encrypted and won't be shown again.`,
            )
          }
        />
      ) : null}

      {dialog.open && dialog.mode === "rotate" ? (
        <ProviderDialog
          mode="rotate"
          credential={dialog.credential}
          credentials={rows ?? []}
          onClose={() => setDialog({ open: false })}
          onSaved={(row) => refreshList(`${PROVIDER_DISPLAY_NAMES[row.provider]} key replaced.`)}
        />
      ) : null}

      {dialog.open && dialog.mode === "delete" ? (
        <DeleteProviderDialog
          credential={dialog.credential}
          onClose={() => setDialog({ open: false })}
          onDeleted={() =>
            refreshList(`${PROVIDER_DISPLAY_NAMES[dialog.credential.provider]} credential removed.`)
          }
        />
      ) : null}
    </Container>
  );
}

function AccountDeletedFarewell() {
  return (
    <Container className="max-w-3xl py-10 sm:py-14">
      <div role="status" className="max-w-xl">
        <p className="font-mono text-xs tracking-[0.2em] text-signal uppercase">Settings</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.02em] text-balance">
          Account deleted
        </h1>
        <p className="mt-4 text-base leading-relaxed text-ink-soft">
          Your account, analyses, uploaded documents, and saved AI provider keys were permanently
          deleted, and you have been signed out. We&apos;re sorry to see you go.
        </p>
        <p className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="inline-flex items-center justify-center rounded-full bg-signal px-5 py-2.5 text-[15px] font-semibold text-white transition outline-none hover:bg-signal-deep focus-visible:ring-2 focus-visible:ring-signal/50"
          >
            Create a new account
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-full border border-line px-5 py-2.5 text-[15px] font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
          >
            Back to home
          </Link>
        </p>
      </div>
    </Container>
  );
}

export function SettingsScreen() {
  const [deleted, setDeleted] = useState(false);
  if (deleted) return <AccountDeletedFarewell />;
  return (
    <ProtectedRoute>
      <SettingsContent onDeleted={() => setDeleted(true)} />
    </ProtectedRoute>
  );
}
