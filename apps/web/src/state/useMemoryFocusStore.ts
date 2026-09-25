/**
 * The one memory a thread asked the memory settings to show. The settings
 * modal opens on it and drops it when it closes.
 */

import type { MemoryKind } from "@pathfinder/shared";

import { createStore } from "./middleware";

interface FocusedMemory {
  key: string;
  kind: MemoryKind;
}

interface MemoryFocusState {
  focused: FocusedMemory | null;
  focusMemory: (key: string, kind: MemoryKind) => void;
  clearFocus: () => void;
}

export const useMemoryFocusStore = createStore<MemoryFocusState>(
  "MemoryFocusStore",
  (set) => ({
    focused: null,
    focusMemory: (key, kind) => set({ focused: { key, kind } }),
    clearFocus: () => set((s) => (s.focused === null ? s : { focused: null })),
  }),
);
