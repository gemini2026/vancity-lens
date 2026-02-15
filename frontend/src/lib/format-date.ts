/**
 * VanCity Lens — Pacific Time Date Formatting Utility (Sprint 10.3)
 *
 * All user-facing timestamps display in Pacific Time (Vancouver).
 * API returns UTC; this module handles the conversion.
 */

const PACIFIC_TZ = "America/Vancouver";

/**
 * Format a date string or Date to Pacific Time for display.
 * Returns "Jan 15, 2026" style.
 */
export function formatDatePT(
  input: string | Date | null | undefined,
): string {
  if (!input) return "—";
  try {
    const d = typeof input === "string" ? new Date(input) : input;
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("en-CA", {
      timeZone: PACIFIC_TZ,
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "—";
  }
}

/**
 * Format a date string or Date to Pacific Time with time.
 * Returns "Jan 15, 2026 3:45 PM PST" style.
 */
export function formatDateTimePT(
  input: string | Date | null | undefined,
): string {
  if (!input) return "—";
  try {
    const d = typeof input === "string" ? new Date(input) : input;
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-CA", {
      timeZone: PACIFIC_TZ,
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return "—";
  }
}

/**
 * Format a relative time string (e.g., "2 hours ago", "3 days ago").
 * Uses Pacific Time for "today" boundary.
 */
export function formatRelativeTimePT(
  input: string | Date | null | undefined,
): string {
  if (!input) return "—";
  try {
    const d = typeof input === "string" ? new Date(input) : input;
    if (isNaN(d.getTime())) return "—";

    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMinutes < 1) return "Just now";
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDatePT(d);
  } catch {
    return "—";
  }
}
