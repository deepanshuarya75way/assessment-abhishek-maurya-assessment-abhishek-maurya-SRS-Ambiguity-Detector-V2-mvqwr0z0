"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

/**
 * Canonical section reveal: fade + 16px lift on the shared expo curve
 * (the project contract). The ONLY entrance pattern until later stages
 * justify additions.
 */
export function Reveal({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.56, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}
