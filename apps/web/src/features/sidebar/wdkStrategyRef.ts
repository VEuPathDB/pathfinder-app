import type { SiteResponse } from "@pathfinder/shared";

/** The strategy id inside a VEuPathDB workspace link, or at the end of one. */
const STRATEGY_IN_URL = /\/strategies\/(\d+)(?:[/?#]|$)/;
const BARE_ID = /^\d+$/;
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;

/**
 * What a researcher's entry names. Strategy ids are per-site sequences, so a
 * link another site serves names no strategy this site can open.
 */
export type WdkStrategyEntry =
  | { kind: "unreadable" }
  | { kind: "thisSite"; wdkStrategyId: number }
  | { kind: "otherSite"; host: string; siteId: string | null };

/** The host a link names, or null when the entry carries none. */
function hostOf(value: string): string | null {
  if (value.startsWith("/")) return null;
  try {
    const url = new URL(HAS_SCHEME.test(value) ? value : `https://${value}`);
    return url.hostname === "" ? null : url.hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

function strategyIdIn(entry: string): number | null {
  const digits = BARE_ID.test(entry)
    ? entry
    : (STRATEGY_IN_URL.exec(entry)?.[1] ?? null);
  if (digits === null) return null;
  const id = Number(digits);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

/**
 * Read a strategy entry against the site the researcher works on. A bare id
 * names no host, so it is read as this site's.
 */
export function readWdkStrategyEntry(
  entry: string,
  siteId: string,
  sites: SiteResponse[],
): WdkStrategyEntry {
  const trimmed = entry.trim();
  const wdkStrategyId = strategyIdIn(trimmed);
  if (wdkStrategyId === null) return { kind: "unreadable" };
  const host = BARE_ID.test(trimmed) ? null : hostOf(trimmed);
  if (host === null) return { kind: "thisSite", wdkStrategyId };
  const named = sites.find((site) => hostOf(site.baseUrl) === host);
  if (named?.id === siteId) return { kind: "thisSite", wdkStrategyId };
  return { kind: "otherSite", host, siteId: named?.id ?? null };
}
