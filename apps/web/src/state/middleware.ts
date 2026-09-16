/**
 * Store factory functions - enforce consistent middleware stacking.
 *
 * Every Zustand store in the app uses one of these two factories.
 * Adding future middleware (e.g. immer) means changing this one file.
 */

import { create } from "zustand";
import { devtools, persist, subscribeWithSelector } from "zustand/middleware";
import type { StateCreator } from "zustand";
import type {} from "@redux-devtools/extension";

const PERSIST_STORAGE_EPOCH = "20260625";
const LOCAL_BROWSER_RESET_MARKER = "pf-local-reset-20260625";

function clearOldPathfinderLocalStorage(): void {
  if (typeof window === "undefined") return;
  try {
    if (window.localStorage.getItem(LOCAL_BROWSER_RESET_MARKER) === "1") return;
    const staleKeys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (
        key != null &&
        (key.startsWith("pathfinder-") || key.startsWith("pathfinder:"))
      ) {
        staleKeys.push(key);
      }
    }
    for (const key of staleKeys) {
      window.localStorage.removeItem(key);
    }
    window.localStorage.setItem(LOCAL_BROWSER_RESET_MARKER, "1");
  } catch {
    // Storage may be unavailable in SSR or hardened browser contexts.
  }
}

/** Middleware mutator tuple for stores wrapped with devtools only. */
export type DevtoolsMutators = [
  ["zustand/subscribeWithSelector", never],
  ["zustand/devtools", never],
];

/** Middleware mutator tuple for stores wrapped with devtools + persist. */
type PersistMutators = [
  ["zustand/subscribeWithSelector", never],
  ["zustand/devtools", never],
  ["zustand/persist", unknown],
];

/** Create a Zustand store with subscribeWithSelector + devtools middleware. */
export function createStore<T>(
  name: string,
  initializer: StateCreator<T, DevtoolsMutators>,
) {
  return create<T>()(subscribeWithSelector(devtools(initializer, { name })));
}

/** Create a Zustand store with subscribeWithSelector + devtools + persist middleware. */
export function createPersistedStore<T>(
  name: string,
  initializer: StateCreator<T, PersistMutators>,
  storage: { name: string; partialize: (state: T) => Partial<T> },
) {
  const storageName = `${storage.name}-${PERSIST_STORAGE_EPOCH}`;
  clearOldPathfinderLocalStorage();
  return create<T>()(
    subscribeWithSelector(
      devtools(persist(initializer, { ...storage, name: storageName }), { name }),
    ),
  );
}
