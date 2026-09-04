"use client";

import { useShallow } from "zustand/react/shallow";
import { useStrategyStore } from "@/state/strategy/store";
import { useStrategyCacheUtils } from "@/lib/api/strategy";

export function useStrategyHistory(conversationId: string) {
  const cache = useStrategyCacheUtils();
  const { pushSnapshot, undo, redo, canUndo, canRedo } = useStrategyStore(
    useShallow((s) => ({
      pushSnapshot: s.pushSnapshot,
      undo: s.undo,
      redo: s.redo,
      canUndo: s.canUndo,
      canRedo: s.canRedo,
    })),
  );

  return {
    pushSnapshot: (prev: { strategy: ReturnType<typeof cache.get> }) =>
      pushSnapshot(prev, cache.get(conversationId)),
    undo: () => {
      const next = undo(cache.get(conversationId));
      if (next !== null) cache.set(conversationId, next);
    },
    redo: () => {
      const next = redo(cache.get(conversationId));
      if (next !== null) cache.set(conversationId, next);
    },
    canUndo,
    canRedo,
  };
}
