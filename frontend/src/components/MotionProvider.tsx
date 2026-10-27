"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/** Global motion posture: honor the OS reduced-motion setting everywhere. */
export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
