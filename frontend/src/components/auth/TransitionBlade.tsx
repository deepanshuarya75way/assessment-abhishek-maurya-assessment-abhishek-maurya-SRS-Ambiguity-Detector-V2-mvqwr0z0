"use client";

/**
 * The Login ↔ Signup sweep: one dark layer translating across the card — via an
 * animated `clip-path` on desktop (slanted side panel docking left/right) and an
 * animated height curtain on mobile (top strip drops to full cover and back).
 * No layout animation of content, no API calls — pure choreography. Geometry
 * matches the card's spacer BY CONSTRUCTION (same fractions / same constant),
 * so the docked blade can never cover live inputs. Reduced motion → static panel.
 */

import { motion, useAnimationControls } from "motion/react";
import { useEffect } from "react";

import { cn } from "@/lib/utils";

export type BladePhase = "idle" | "covering" | "covered" | "revealing";

/** Resting side on desktop (mobile always docks the strip on top). */
export type BladeSide = "left" | "right";

const COVER = "polygon(0% 0%, 100% 0%, 100% 100%, 0% 100%)";
/** 40% panel, slanted leading edge (matches the card's 3/5 + 2/5 grid). */
const REST_RIGHT = "polygon(63% 0%, 100% 0%, 100% 100%, 59% 100%)";
const REST_LEFT = "polygon(0% 0%, 41% 0%, 37% 100%, 0% 100%)";
/** Mobile strip rest height — the card's spacer uses this same constant. */
export const BLADE_STRIP_PX = 148;

const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];
const SWEEP_SECONDS = 0.32;

export interface TransitionBladeProps {
  side: BladeSide;
  phase: BladePhase;
  /** Stacked (mobile) layout — strip on top instead of a side panel. */
  vertical: boolean;
  /** False under reduced-motion: static panel, no animation. */
  animated: boolean;
  /** Full-cover height for the mobile curtain (measured card height + margin). */
  coverH: number;
  eyebrow: string;
  pitch: string;
  actionLabel: string;
  onSwitch: () => void;
}

export function TransitionBlade({
  side,
  phase,
  vertical,
  animated,
  coverH,
  eyebrow,
  pitch,
  actionLabel,
  onSwitch,
}: TransitionBladeProps) {
  const controls = useAnimationControls();
  const sweeping = animated && phase !== "idle";
  const restClip = side === "right" ? REST_RIGHT : REST_LEFT;

  useEffect(() => {
    if (!animated) return;
    // Both geometry props are set on every branch so a breakpoint flip mid-life
    // can never leave a stale inline height or clip behind.
    if (phase === "covering") {
      void controls.start(
        vertical
          ? {
              height: coverH,
              clipPath: "none",
              transition: { duration: SWEEP_SECONDS, ease: EASE },
            }
          : {
              clipPath: COVER,
              height: "auto",
              transition: { duration: SWEEP_SECONDS, ease: EASE },
            },
      );
    } else if (phase === "revealing") {
      void controls.start(
        vertical
          ? {
              height: BLADE_STRIP_PX,
              clipPath: "none",
              transition: { duration: SWEEP_SECONDS, ease: EASE },
            }
          : {
              clipPath: restClip,
              height: "auto",
              transition: { duration: SWEEP_SECONDS, ease: EASE },
            },
      );
    } else if (phase === "covered") {
      controls.set(vertical ? { height: coverH, clipPath: "none" } : { clipPath: COVER });
    } else {
      controls.set(
        vertical ? { height: BLADE_STRIP_PX, clipPath: "none" } : { clipPath: restClip },
      );
    }
  }, [animated, phase, side, vertical, coverH, controls, restClip]);

  return (
    <motion.div
      aria-hidden={sweeping}
      initial={vertical ? { height: BLADE_STRIP_PX } : { clipPath: restClip }}
      animate={animated ? controls : undefined}
      style={
        !animated ? (vertical ? { height: BLADE_STRIP_PX } : { clipPath: restClip }) : undefined
      }
      className={
        vertical
          ? "absolute inset-x-0 top-0 z-10 overflow-hidden bg-ink text-paper"
          : "absolute inset-0 z-10 overflow-hidden bg-ink text-paper"
      }
    >
      <motion.div
        initial={false}
        animate={
          animated ? { opacity: phase === "idle" || phase === "revealing" ? 1 : 0 } : undefined
        }
        transition={{ duration: 0.18 }}
        inert={sweeping}
        className="h-full w-full"
      >
        {vertical ? (
          /* Mobile strip — compact row that drops like a curtain mid-sweep. */
          <div className="flex h-[148px] items-center justify-between gap-3 px-5">
            <div className="min-w-0">
              <p className="font-mono text-[10px] font-medium tracking-[0.18em] text-gold">
                {eyebrow}
              </p>
              <p className="mt-0.5 truncate text-[14px] font-medium text-paper">{pitch}</p>
            </div>
            <button
              type="button"
              onClick={onSwitch}
              tabIndex={sweeping ? -1 : undefined}
              className="shrink-0 rounded-lg border border-gold/60 px-3.5 py-2 text-[13px] font-semibold text-gold outline-none transition hover:bg-gold hover:text-ink focus-visible:ring-2 focus-visible:ring-gold/60"
            >
              {actionLabel}
            </button>
          </div>
        ) : (
          /* Desktop docked panel. */
          <div
            className={cn("flex h-full w-full", side === "right" ? "justify-end" : "justify-start")}
          >
            <div className="flex h-full w-[40%] flex-col justify-center px-8">
              <p aria-hidden className="font-mono text-[13px] tracking-[0.2em] text-gold/80">
                §
              </p>
              <p className="mt-3 font-mono text-[11px] font-medium tracking-[0.18em] text-gold">
                {eyebrow}
              </p>
              <p className="mt-2 text-[19px] font-semibold leading-snug text-paper">{pitch}</p>
              <div aria-hidden className="my-5 h-px w-10 bg-gold/60" />
              <div>
                <button
                  type="button"
                  onClick={onSwitch}
                  tabIndex={sweeping ? -1 : undefined}
                  className="rounded-xl border border-gold/60 px-5 py-2.5 text-[14px] font-semibold text-gold outline-none transition hover:bg-gold hover:text-ink focus-visible:ring-2 focus-visible:ring-gold/60"
                >
                  {actionLabel}
                </button>
              </div>
              <p className="mt-6 font-mono text-[10px] leading-relaxed tracking-[0.14em] text-paper/50">
                SESSIONS IN HTTPONLY
                <br />
                COOKIES — NEVER IN JS
              </p>
            </div>
          </div>
        )}
      </motion.div>
      {/* Gold leading line — rides the curtain's bottom edge on mobile. */}
      {vertical ? (
        <div aria-hidden className="absolute inset-x-0 bottom-0 h-px bg-gold/70" />
      ) : null}
    </motion.div>
  );
}
