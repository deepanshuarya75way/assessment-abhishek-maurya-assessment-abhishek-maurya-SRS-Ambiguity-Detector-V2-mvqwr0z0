"use client";

/**
 * Profile section (Stage 16): the caller's own identity — read-only email
 * (address changes are NOT in v1) plus an editable display name. Self-contained
 * fetch states (skeleton / session-gone / load-failed + retry) so a profile
 * outage never blocks the provider list and vice versa. Saves re-read from the
 * server (the PATCH response IS the fresh row) and sync the global identity via
 * `refreshUser`, so a stale display name never lingers in the app shell.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { TriangleAlert } from "lucide-react";

import { FormAlert, SubmitButton, TextField } from "@/components/auth/fields";
import { useAuth } from "@/hooks/useAuth";
import { ApiRequestError } from "@/lib/api";
import { isSessionGone } from "@/lib/auth";
import { getProfile, updateProfile } from "@/lib/settings";
import { settingsErrorMessage } from "@/lib/settings-errors";
import type { Profile } from "@/types/settings";

const UNEXPECTED_RESPONSE = "The service returned an unexpected response.";

type LoadState =
  | { status: "loading" }
  | { status: "session-gone" }
  | { status: "load-failed"; message: string }
  | { status: "ready"; profile: Profile };

function isProfile(data: unknown): data is Profile {
  if (typeof data !== "object" || data === null) return false;
  const candidate = data as Record<string, unknown>;
  return (
    typeof candidate.email === "string" &&
    (candidate.display_name === null || typeof candidate.display_name === "string") &&
    typeof candidate.is_verified === "boolean" &&
    typeof candidate.is_active === "boolean" &&
    typeof candidate.created_at === "string"
  );
}

export function ProfileSection() {
  const { refreshUser } = useAuth();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [refreshKey, setRefreshKey] = useState(0);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProfile().then(
      (data: unknown) => {
        if (cancelled) return;
        if (!isProfile(data)) {
          setState({ status: "load-failed", message: UNEXPECTED_RESPONSE });
          return;
        }
        setName(data.display_name ?? "");
        setState({ status: "ready", profile: data });
      },
      (err: unknown) => {
        if (cancelled) return;
        if (isSessionGone(err)) setState({ status: "session-gone" });
        else setState({ status: "load-failed", message: settingsErrorMessage(err, "load") });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || state.status !== "ready") return;
    setNameError(undefined);
    setFormError(null);
    setSaved(false);
    setPending(true);
    try {
      const fresh: unknown = await updateProfile({ display_name: name.trim() || null });
      if (!isProfile(fresh)) {
        setFormError(UNEXPECTED_RESPONSE);
        return;
      }
      setName(fresh.display_name ?? "");
      setState({ status: "ready", profile: fresh });
      setSaved(true);
      // Best-effort identity sync: refreshUser never throws (unresolvable →
      // honest unauthenticated state), so a blip can't fake a success.
      await refreshUser();
    } catch (err) {
      if (isSessionGone(err)) {
        setState({ status: "session-gone" });
        return;
      }
      const message = settingsErrorMessage(err, "save");
      // Field-shaped failures land on the field (single announcement); anything
      // else goes form-level. Never both — duplicate copy confuses SR users.
      if (err instanceof ApiRequestError && err.code === "validation_error") {
        setNameError(message);
      } else {
        setFormError(message);
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="profile-heading" className="mt-10">
      <h2 id="profile-heading" className="text-2xl font-semibold tracking-[-0.02em]">
        Profile
      </h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
        How you appear across the app. Your email address signs you in and receives security notices
        — it can&apos;t be changed here.
      </p>

      {state.status === "loading" ? (
        <div
          aria-busy="true"
          aria-label="Loading profile"
          className="mt-6 rounded-card border border-line bg-paper p-8"
        >
          <div className="animate-pulse space-y-3">
            <div className="h-4 w-48 rounded bg-paper-deep" />
            <div className="h-10 w-full rounded-xl bg-paper-deep" />
          </div>
        </div>
      ) : null}

      {state.status === "session-gone" ? (
        <div role="status" className="mt-6 max-w-xl">
          <p className="text-[15px] leading-relaxed text-ink-soft">
            Your session expired before your profile loaded.{" "}
            <Link
              href="/login"
              className="font-semibold text-signal underline underline-offset-2 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
            >
              Sign in again
            </Link>
          </p>
        </div>
      ) : null}

      {state.status === "load-failed" ? (
        <div
          role="alert"
          className="mt-6 flex max-w-xl items-start gap-3 rounded-card border border-line bg-paper p-5"
        >
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-gold" aria-hidden />
          <div>
            <p className="text-[15px] leading-relaxed text-ink-soft">{state.message}</p>
            <button
              type="button"
              onClick={() => {
                setState({ status: "loading" });
                setRefreshKey((count) => count + 1);
              }}
              className="mt-4 inline-flex items-center justify-center rounded-full border border-line px-5 py-2 text-sm font-medium text-ink-soft transition outline-none hover:bg-paper-deep focus-visible:ring-2 focus-visible:ring-signal/50"
            >
              Retry
            </button>
          </div>
        </div>
      ) : null}

      {state.status === "ready" ? (
        <form
          noValidate
          onSubmit={handleSubmit}
          aria-label="Edit profile"
          className="mt-6 max-w-xl space-y-4"
        >
          <fieldset disabled={pending} className="m-0 space-y-4 border-0 p-0">
            {formError ? <FormAlert kind="error">{formError}</FormAlert> : null}
            {saved ? <FormAlert kind="success">Profile saved.</FormAlert> : null}
            <div>
              <p className="mb-1.5 text-[13px] font-medium text-ink-soft">Email</p>
              <p className="truncate rounded-xl border border-line bg-paper-deep px-3.5 py-2.5 text-[15px] text-ink-soft">
                {state.profile.email}
              </p>
            </div>
            <TextField
              label="Display name"
              name="display_name"
              autoComplete="nickname"
              value={name}
              maxLength={100}
              hint="Shown across the app. Leave blank to clear it."
              onChange={(value) => {
                setName(value);
                setNameError(undefined);
              }}
              error={nameError}
            />
            <SubmitButton pending={pending} pendingLabel="Saving…">
              Save profile
            </SubmitButton>
          </fieldset>
        </form>
      ) : null}
    </section>
  );
}
