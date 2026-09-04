/**
 * Time formatting utilities for the UI.
 *
 * All formatters use the browser's local timezone (i.e. the user's timezone)
 * via ``Intl.DateTimeFormat`` / ``Date.toLocaleString``.
 */

/**
 * Format an ISO timestamp as a short time string for chat messages.
 *
 * Returns e.g. ``"2:34 PM"`` when the message is from today,
 * or ``"Feb 14, 2:34 PM"`` when it's from a different day.
 *
 * :param iso: ISO 8601 timestamp string.
 * :returns: A human-readable time string in the user's local timezone.
 */
export function formatMessageTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (isToday) {
    return date.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Format an ISO timestamp for the conversation sidebar.
 *
 * Returns a relative or short date-time string in the user's local timezone:
 * - Today: ``"2:34 PM"``
 * - Yesterday: ``"Yesterday"``
 * - This year: ``"Feb 14"``
 * - Older: ``"Feb 14, 2025"``
 *
 * :param iso: ISO 8601 timestamp string.
 * :returns: A human-readable date string in the user's local timezone.
 */
export function formatSidebarTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();

  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (isToday) {
    return date.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate();

  if (isYesterday) return "Yesterday";

  if (date.getFullYear() === now.getFullYear()) {
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
