"use client";

import { useEventListener } from "usehooks-ts";

import { useStrategyAutoFlush } from "./useStrategyAutoFlush";

/**
 * Listens for browser back/forward navigation (popstate) and triggers the
 * same `awaitFlush()` used by in-app navigation so optimistic strategy edits
 * land before the next page mounts.
 *
 * Caveat: popstate fires AFTER the URL has already changed. We can't block
 * navigation. The best we can do is fire the flush as soon as we hear the
 * event so any in-flight push completes before React mounts the next route's
 * components. If the page transition is faster than the network round-trip,
 * a pending push may still be in flight when the next page mounts - but the
 * mutation cache lives on the QueryClient (which is app-wide), so it
 * continues to settle in the background and `awaitFlush` keeps blocking until
 * it does.
 *
 * Mount this hook at the conversation layout level so it's active whenever
 * the user could be on (or returning from) a strategy surface.
 */
export function useStrategyPopstateFlush(): void {
  const { awaitFlush } = useStrategyAutoFlush();
  useEventListener("popstate", () => {
    void awaitFlush();
  });
}
