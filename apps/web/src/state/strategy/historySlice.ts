import { enablePatches, produceWithPatches, applyPatches } from "immer";
import type { Patch } from "immer";
import type { StateCreator } from "zustand";
import type { DevtoolsMutators } from "@/state/middleware";
import type { HistorySlice, HistorySnapshot, StrategyState } from "./types";

enablePatches();

const MAX_HISTORY = 50;
const REDO_CLEARED_BY = new WeakMap<Patch[], Patch[][]>();

function trimStack(stack: Patch[][]): Patch[][] {
  while (stack.length > MAX_HISTORY) {
    stack.shift();
  }
  return stack;
}

function inversePatchesBetween(prev: HistorySnapshot, next: HistorySnapshot): Patch[] {
  const [, , inverse] = produceWithPatches(prev, (draft) => {
    draft.strategy = next.strategy;
  });
  return inverse;
}

export const createHistorySlice: StateCreator<
  StrategyState,
  DevtoolsMutators,
  [],
  HistorySlice
> = (set, get) => ({
  undoStack: [],
  redoStack: [],

  pushSnapshot: (prev, current) => {
    if (prev.strategy === null) return null;
    const inverse = inversePatchesBetween(prev, { strategy: current });
    if (inverse.length === 0) return null;
    REDO_CLEARED_BY.set(inverse, get().redoStack);
    set((state) => ({
      undoStack: trimStack([...state.undoStack, inverse]),
      redoStack: [],
    }));
    return inverse;
  },

  dropSnapshot: (inverse) => {
    const { undoStack } = get();
    const at = undoStack.indexOf(inverse);
    if (at === -1) return;
    const remaining = undoStack.filter((entry) => entry !== inverse);
    const cleared = REDO_CLEARED_BY.get(inverse) ?? [];
    const above = undoStack[at + 1];
    if (above === undefined) {
      set({ undoStack: remaining, redoStack: cleared });
      return;
    }
    REDO_CLEARED_BY.set(above, cleared);
    set({ undoStack: remaining });
  },

  undo: (current) => {
    const { undoStack, redoStack } = get();
    const lastInverse = undoStack[undoStack.length - 1];
    if (!lastInverse) return null;

    const [restored, , forward] = produceWithPatches(
      { strategy: current } satisfies HistorySnapshot,
      (draft) => {
        applyPatches(draft, lastInverse);
      },
    );

    set({
      undoStack: undoStack.slice(0, -1),
      redoStack: [...redoStack, forward],
    });
    return restored.strategy;
  },

  redo: (current) => {
    const { undoStack, redoStack } = get();
    const lastForward = redoStack[redoStack.length - 1];
    if (!lastForward) return null;

    const [restored, , inverse] = produceWithPatches(
      { strategy: current } satisfies HistorySnapshot,
      (draft) => {
        applyPatches(draft, lastForward);
      },
    );

    set({
      undoStack: [...undoStack, inverse],
      redoStack: redoStack.slice(0, -1),
    });
    return restored.strategy;
  },

  canUndo: () => get().undoStack.length > 0,
  canRedo: () => get().redoStack.length > 0,

  clearHistory: () => set({ undoStack: [], redoStack: [] }),
});
