"use client";

/**
 * Privacy section (Stage 23): real lifecycle controls only. Retention settings,
 * data export tickets, and purge-history actions all call live backend endpoints;
 * no disabled/fake controls are shown.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { authErrorMessage } from "@/lib/auth-errors";
import {
  apiDownloadUrl,
  createPrivacyExport,
  getPrivacySettings,
  purgeHistory,
  updatePrivacySettings,
} from "@/lib/privacy";

function parseDays(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 3650) return Number.NaN;
  return parsed;
}

export function PrivacySection() {
  const [loading, setLoading] = useState(true);
  const [retentionDays, setRetentionDays] = useState("");
  const [purgeDays, setPurgeDays] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<"settings" | "export" | "purge" | null>(null);
  const [exportUrl, setExportUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPrivacySettings().then(
      (settings) => {
        if (cancelled) return;
        setRetentionDays(settings.history_retention_days?.toString() ?? "");
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setError(authErrorMessage(err, "session"));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveSettings(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseDays(retentionDays);
    setError(null);
    setMessage(null);
    setExportUrl(null);
    if (Number.isNaN(parsed)) {
      setError("Enter 1 to 3650 days, or leave blank to disable automatic retention.");
      return;
    }
    setPending("settings");
    try {
      const saved = await updatePrivacySettings({ history_retention_days: parsed });
      setRetentionDays(saved.history_retention_days?.toString() ?? "");
      setMessage(
        saved.history_retention_days === null
          ? "Automatic history retention is disabled."
          : `Automatic history retention is set to ${saved.history_retention_days} days.`,
      );
    } catch (err) {
      setError(authErrorMessage(err, "session"));
    } finally {
      setPending(null);
    }
  }

  async function requestExport() {
    setError(null);
    setMessage(null);
    setExportUrl(null);
    setPending("export");
    try {
      const ticket = await createPrivacyExport();
      setExportUrl(apiDownloadUrl(ticket.download_url));
      setMessage("Export link created. It expires shortly and still requires your session.");
    } catch (err) {
      setError(authErrorMessage(err, "session"));
    } finally {
      setPending(null);
    }
  }

  async function runPurge(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseDays(purgeDays || retentionDays);
    setError(null);
    setMessage(null);
    setExportUrl(null);
    if (Number.isNaN(parsed) || parsed === null) {
      setError("Enter 1 to 3650 days, or save a retention window first.");
      return;
    }
    setPending("purge");
    try {
      const result = await purgeHistory({ older_than_days: parsed });
      setMessage(
        `Purged ${result.deleted_analyses} analyses and ${result.deleted_documents} stored documents older than ${parsed} days.`,
      );
    } catch (err) {
      setError(authErrorMessage(err, "session"));
    } finally {
      setPending(null);
    }
  }

  return (
    <section aria-labelledby="privacy-heading" className="mt-10">
      <h2 id="privacy-heading" className="text-2xl font-semibold tracking-[-0.02em]">
        Privacy
      </h2>
      <div className="mt-4 max-w-2xl space-y-4 text-[15px] leading-relaxed text-ink-soft">
        <p>
          Your account holds your analyses and uploaded documents plus, if you added any, your AI
          provider keys — stored encrypted and never shown again after saving. Nothing here is
          shared with other accounts.
        </p>
        <p>
          Deleting an analysis in History removes it permanently, including its uploaded file when
          that file is no longer referenced. Deleting your account below removes profile data,
          analyses, documents, storage objects, sessions, password-reset tokens, and saved
          provider-key ciphertext.
        </p>
        <p>
          Export includes profile data, analysis/report content, document metadata, and provider
          metadata only. It never includes passwords, session tokens, password-reset tokens,
          provider API keys, encrypted key ciphertext, storage paths, or stored file bytes.
        </p>

        {loading ? <p className="text-sm text-ink-faint">Loading privacy settings…</p> : null}
        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-sev-crit/30 bg-sev-crit/10 p-3 text-sm text-sev-crit"
          >
            {error}
          </p>
        ) : null}
        {message ? (
          <p
            role="status"
            className="rounded-lg border border-signal/20 bg-signal/10 p-3 text-sm text-signal-deep"
          >
            {message}
          </p>
        ) : null}
        {exportUrl ? (
          <a
            href={exportUrl}
            className="inline-flex rounded-full border border-signal/30 px-4 py-2 text-sm font-semibold text-signal outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
          >
            Download privacy export
          </a>
        ) : null}

        <form onSubmit={saveSettings} className="rounded-2xl border border-line bg-white/45 p-4">
          <label htmlFor="history-retention-days" className="block font-medium text-ink">
            Automatic history retention
          </label>
          <p className="mt-1 text-sm text-ink-soft">
            Keep blank to retain history until you delete it. Enter 1–3650 days to let the
            maintenance purge remove older analyses and their unreferenced stored documents.
          </p>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row">
            <input
              id="history-retention-days"
              inputMode="numeric"
              pattern="[0-9]*"
              value={retentionDays}
              onChange={(event) => setRetentionDays(event.target.value)}
              placeholder="No automatic purge"
              className="min-h-11 flex-1 rounded-lg border border-line bg-paper px-3 text-ink outline-none focus:ring-2 focus:ring-signal/40"
            />
            <button
              type="submit"
              disabled={pending !== null || loading}
              className="btn-primary justify-center disabled:opacity-60"
            >
              {pending === "settings" ? "Saving…" : "Save retention"}
            </button>
          </div>
        </form>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-line bg-white/45 p-4">
            <h3 className="font-semibold text-ink">Data export</h3>
            <p className="mt-1 text-sm text-ink-soft">
              Create a short-lived export link for the safe, allowlisted data described above.
            </p>
            <button
              type="button"
              onClick={requestExport}
              disabled={pending !== null || loading}
              className="btn-secondary mt-3 justify-center disabled:opacity-60"
            >
              {pending === "export" ? "Creating…" : "Create export link"}
            </button>
          </div>

          <form onSubmit={runPurge} className="rounded-2xl border border-line bg-white/45 p-4">
            <label htmlFor="purge-history-days" className="block font-semibold text-ink">
              Purge old history now
            </label>
            <p className="mt-1 text-sm text-ink-soft">
              Permanently remove analyses older than this many days. Leave blank to use the saved
              retention value.
            </p>
            <input
              id="purge-history-days"
              inputMode="numeric"
              pattern="[0-9]*"
              value={purgeDays}
              onChange={(event) => setPurgeDays(event.target.value)}
              placeholder={retentionDays || "Days"}
              className="mt-3 min-h-11 w-full rounded-lg border border-line bg-paper px-3 text-ink outline-none focus:ring-2 focus:ring-signal/40"
            />
            <button
              type="submit"
              disabled={pending !== null || loading}
              className="btn-secondary mt-3 justify-center disabled:opacity-60"
            >
              {pending === "purge" ? "Purging…" : "Purge old history"}
            </button>
          </form>
        </div>

        <p>
          You can still manage individual analyses in{" "}
          <Link
            href="/history"
            className="font-semibold text-signal underline underline-offset-2 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
          >
            History
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
