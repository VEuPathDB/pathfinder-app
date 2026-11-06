import type { ThreadMode } from "@pathfinder/shared/generated/types/ThreadMode";

import { createStore } from "./middleware";

interface ThreadModeState {
  modes: Record<string, ThreadMode>;
  setMode: (conversationId: string, mode: ThreadMode) => void;
}

export const useThreadModeStore = createStore<ThreadModeState>(
  "ThreadModeStore",
  (set) => ({
    modes: {},
    setMode: (conversationId, mode) =>
      set((s) => ({ modes: { ...s.modes, [conversationId]: mode } })),
  }),
);
