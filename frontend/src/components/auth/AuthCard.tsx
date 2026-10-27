"use client";

/**
 * The login/signup card — one component hosting both forms with the blade/sweep
 * transition between them. Phase machine (timeout-driven, animation-agnostic):
 * idle → covering → covered (mode swaps invisibly) → revealing → idle.
 * Both forms stay mounted; the inactive one is `hidden` + `inert` + `aria-hidden`,
 * and BOTH go inert mid-sweep. Focus moves to the new form's first field when
 * the sweep settles; screen readers get a polite announcement of the change.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useReducedMotionConfig } from "motion/react";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/hooks/useAuth";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { AUTH_LANDING_PATH } from "@/lib/auth";
import { cn } from "@/lib/utils";

import { LoginForm } from "./LoginForm";
import { SignupForm } from "./SignupForm";
import { BLADE_STRIP_PX, TransitionBlade, type BladePhase } from "./TransitionBlade";

export type AuthMode = "login" | "signup";

/** Sweep timings — must match TransitionBlade's SWEEP_SECONDS (0.32s). */
const COVER_MS = 320;
const HOLD_MS = 60;
const REVEAL_MS = 320;

const HEADER_COPY: Record<AuthMode, { title: string; lede: string }> = {
  login: { title: "Welcome back", lede: "Log in to pick up where you left off." },
  signup: { title: "Create your account", lede: "One account for every spec you'll check." },
};

/** Blade invites the OTHER mode, so this is keyed by the current one. */
const BLADE_COPY: Record<
  AuthMode,
  { eyebrow: string; pitch: string; actionLabel: string; target: AuthMode }
> = {
  login: {
    eyebrow: "NEW HERE?",
    pitch: "Create an account to start checking specs.",
    actionLabel: "Create account",
    target: "signup",
  },
  signup: {
    eyebrow: "ALREADY WITH US?",
    pitch: "Log in to pick up where you left off.",
    actionLabel: "Log in",
    target: "login",
  },
};

function AuthCardSkeleton() {
  return (
    <div className="w-full max-w-3xl">
      <div
        aria-busy="true"
        aria-label="Loading account access"
        className="overflow-hidden rounded-2xl border border-line bg-white shadow-xl"
      >
        <div className="animate-pulse space-y-4 p-6 sm:p-10">
          <div className="h-7 w-48 rounded-lg bg-paper-deep" />
          <div className="h-4 w-72 rounded bg-paper-deep" />
          <div className="space-y-3 pt-4">
            <div className="h-11 rounded-xl bg-paper-deep" />
            <div className="h-11 rounded-xl bg-paper-deep" />
            <div className="h-11 rounded-xl bg-paper-deep" />
          </div>
        </div>
      </div>
    </div>
  );
}

function AuthFooter() {
  return (
    <div className="flex items-center justify-between gap-4 border-t border-line bg-paper px-6 py-4 sm:px-10">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 rounded-md text-[13px] font-medium text-ink-soft outline-none transition hover:text-ink focus-visible:ring-2 focus-visible:ring-signal/40"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to home
      </Link>
      <p className="hidden font-mono text-[11px] tracking-wide text-ink-faint min-[420px]:block">
        PASSWORDS HASHED WITH ARGON2ID
      </p>
    </div>
  );
}

export function AuthCard({ initialMode }: { initialMode: AuthMode }) {
  const router = useRouter();
  const { status } = useAuth();
  // Config-aware (not the device-only hook): honors MotionConfig's always/never.
  const reduceMotion = useReducedMotionConfig();
  const wide = useMediaQuery("(min-width: 640px)");
  const vertical = !wide;

  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [phase, setPhase] = useState<BladePhase>("idle");
  const [announcement, setAnnouncement] = useState("");
  const [cardH, setCardH] = useState(0);

  const cardRef = useRef<HTMLDivElement>(null);
  const formRefs = useRef<Record<AuthMode, HTMLElement | null>>({ login: null, signup: null });
  const timers = useRef<number[]>([]);
  /** Synchronous re-entry guard — state updates are async, double-clicks aren't. */
  const busyRef = useRef(false);

  // Authenticated visitors do not need the login or signup pages.
  useEffect(() => {
    if (status === "authenticated") {
      router.replace(AUTH_LANDING_PATH);
    }
  }, [status, router]);

  // Measure the card for the mobile curtain's full-cover height.
  useEffect(() => {
    const el = cardRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      setCardH(Math.ceil(entries[0]?.contentRect.height ?? 0));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Sweep timers die with the card — no setState after unmount, ever.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const id of pending) window.clearTimeout(id);
      pending.length = 0;
    };
  }, []);

  const later = useCallback((ms: number, fn: () => void) => {
    timers.current.push(window.setTimeout(fn, ms));
  }, []);

  const focusFirstField = useCallback((target: AuthMode) => {
    formRefs.current[target]?.querySelector<HTMLElement>("input:not([disabled])")?.focus();
  }, []);

  const requestMode = useCallback(
    (next: AuthMode) => {
      if (next === mode || busyRef.current) return;
      busyRef.current = true;
      const message =
        next === "signup" ? "Showing the create-account form." : "Showing the log-in form.";
      if (reduceMotion) {
        setMode(next);
        setAnnouncement(message);
        // The target form un-hides on re-render — focus after the flush.
        later(0, () => {
          focusFirstField(next);
          busyRef.current = false;
        });
        return;
      }
      setAnnouncement(message);
      setPhase("covering");
      later(COVER_MS, () => {
        setMode(next);
        setPhase("covered");
        later(HOLD_MS, () => {
          setPhase("revealing");
          later(REVEAL_MS, () => {
            setPhase("idle");
            focusFirstField(next);
            busyRef.current = false;
          });
        });
      });
    },
    [mode, reduceMotion, later, focusFirstField],
  );

  if (status === "loading") return <AuthCardSkeleton />;
  if (status === "authenticated") return null;

  const header = HEADER_COPY[mode];
  const blade = BLADE_COPY[mode];
  const sweeping = phase !== "idle";
  const coverH = cardH > 0 ? Math.ceil(cardH * 1.25) : 640;

  return (
    <div className="w-full max-w-3xl">
      <div
        ref={cardRef}
        aria-busy={sweeping}
        className="relative overflow-hidden rounded-2xl border border-line bg-white shadow-xl"
      >
        <p aria-live="polite" className="sr-only">
          {announcement}
        </p>
        <div className="flex flex-col sm:grid sm:grid-cols-5">
            {/* Spacer the blade docks over — fixed strip on mobile, side column up. */}
            <div
              aria-hidden
              className={cn(
                "order-1 shrink-0 sm:col-span-2",
                mode === "login" ? "sm:order-2" : "sm:order-1",
              )}
              style={vertical ? { height: BLADE_STRIP_PX } : undefined}
            />
            <div
              className={cn(
                "order-2 sm:col-span-3",
                mode === "login" ? "sm:order-1" : "sm:order-2",
              )}
            >
              <div className="px-6 py-8 sm:px-10 sm:py-10">
                <h1 className="text-[26px] font-semibold tracking-tight text-ink">
                  {header.title}
                </h1>
                <p className="mt-1.5 text-[15px] leading-relaxed text-ink-soft">{header.lede}</p>
                <div className="mt-6">
                  <section
                    ref={(el) => {
                      formRefs.current.login = el;
                    }}
                    aria-label="Log-in form"
                    aria-hidden={mode !== "login"}
                    inert={mode !== "login" || sweeping}
                    className={cn(mode !== "login" && "hidden")}
                  >
                    <LoginForm onSuccess={() => router.replace(AUTH_LANDING_PATH)} />
                  </section>
                  <section
                    ref={(el) => {
                      formRefs.current.signup = el;
                    }}
                    aria-label="Create-account form"
                    aria-hidden={mode !== "signup"}
                    inert={mode !== "signup" || sweeping}
                    className={cn(mode !== "signup" && "hidden")}
                  >
                    <SignupForm onSuccess={() => router.replace(AUTH_LANDING_PATH)} />
                  </section>
                </div>
              </div>
            </div>
            <TransitionBlade
              side={mode === "login" ? "right" : "left"}
              phase={phase}
              vertical={vertical}
              animated={!reduceMotion}
              coverH={coverH}
              eyebrow={blade.eyebrow}
              pitch={blade.pitch}
              actionLabel={blade.actionLabel}
              onSwitch={() => requestMode(blade.target)}
            />
          </div>
        <AuthFooter />
      </div>
    </div>
  );
}
