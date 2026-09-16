/**
 * Persistent session id for correlating frontend traces across reloads.
 *
 * Generated once per browser, stored in localStorage, and attached to every
 * span as `session.id`. This lets SigNoz filter the full flow a single user
 * went through - click -> fetch -> backend pipeline - by one stable key.
 * No PII is stored; the id is a random v4 UUID.
 */

const STORAGE_KEY = "pathfinder.telemetry.sessionId";

export function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "server";
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing !== null && existing.length > 0) return existing;
    const fresh = crypto.randomUUID();
    window.localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    // Private mode, quota exceeded, etc. - fall back to a per-tab id.
    return crypto.randomUUID();
  }
}
