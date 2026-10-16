import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class names with clsx conflict resolution.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format numbers with US locale formatting (e.g. 12,345).
 */
export function formatNumber(val: number | string): string {
  if (typeof val === "number") {
    return val.toLocaleString("en-US");
  }
  const parsed = Number(val);
  return isNaN(parsed) ? String(val) : parsed.toLocaleString("en-US");
}

/**
 * Format currency with US locale formatting (e.g. $12,345).
 */
export function formatCurrency(val: number | string): string {
  if (typeof val === "number") {
    return `$${val.toLocaleString("en-US")}`;
  }
  const parsed = Number(val);
  return isNaN(parsed) ? String(val) : `$${parsed.toLocaleString("en-US")}`;
}
