import { enablePatches, produceWithPatches, applyPatches } from "immer";
import type { Patch } from "immer";
import type { StateCreator } from "zustand";
import type { DevtoolsMutators } from "@/state/middleware";
import type { HistorySlice, HistorySnapshot, StrategyState } from "./types";

enablePatches();

const MAX_HISTORY = 50;

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
    if (prev.strategy === null) return;
    const inverse = inversePatchesBetween(prev, { strategy: current });
    if (inverse.length === 0) return;
    set((state) => ({
      undoStack: trimStack([...state.undoStack, inverse]),
      redoStack: [],
    }));
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
