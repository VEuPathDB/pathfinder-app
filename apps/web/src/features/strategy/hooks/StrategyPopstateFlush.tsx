"use client";

import { useStrategyPopstateFlush } from "./useStrategyPopstateFlush";

/**
 * Mount-only client component that activates the popstate flush listener.
 * Renders nothing - its sole purpose is to install the listener at a
 * top-level always-mounted location (the conversation layout).
 */
export function StrategyPopstateFlush(): null {
  useStrategyPopstateFlush();
  return null;
}
