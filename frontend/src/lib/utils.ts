import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class lists (canonical `cn` helper — use everywhere). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
