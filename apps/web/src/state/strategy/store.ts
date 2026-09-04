/**
 * Composed strategy store. The draft and meta state lives here directly; the
 * history and lifecycle reducers are big enough to own their own modules.
 */

import { createStore } from "@/state/middleware";
import type { StrategyState } from "./types";
import { createHistorySlice } from "./historySlice";
import { createLifecycleSlice } from "./lifecycleSlice";

export const useStrategyStore = createStore<StrategyState>(
  "StrategyStore",
  (...args) => {
    const [set] = args;
    return {
      ...createHistorySlice(...args),
      ...createLifecycleSlice(...args),

      lastFailedOperation: null,
      graphValidationStatus: {},

      setLastFailedOperation: (payload) => {
        set({ lastFailedOperation: payload });
      },

      setGraphValidationStatus: (id, hasErrors) =>
        set((state) => ({
          graphValidationStatus: {
            ...state.graphValidationStatus,
            [id]: hasErrors,
          },
        })),

      clear: () => {
        set({
          lastFailedOperation: null,
          stepLifecycleById: {},
          undoStack: [],
          redoStack: [],
        });
      },
    };
  },
);
