"use client";

import { useSyncExternalStore } from "react";

const subscribeToNothing = () => () => {};

export function usePageOrigin(): string | null {
  return useSyncExternalStore(
    subscribeToNothing,
    () => window.location.origin,
    () => null,
  );
}
