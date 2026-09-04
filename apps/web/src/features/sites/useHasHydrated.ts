"use client";

import { useSyncExternalStore } from "react";

export function useHasHydrated(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}
