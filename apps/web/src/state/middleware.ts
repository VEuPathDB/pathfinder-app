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
  storage: {
    name: string;
    partialize: (state: T) => Partial<T>;
    merge?: (stored: unknown, current: T) => T;
  },
) {
  const storageName = `${storage.name}-${PERSIST_STORAGE_EPOCH}`;
  return create<T>()(
    subscribeWithSelector(
      devtools(persist(initializer, { ...storage, name: storageName }), { name }),
    ),
  );
}
