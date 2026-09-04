import type { UIMessage } from "ai";

export interface RailActivity {
  ledgerCount: number;
  scratchpadCount: number;
  taskCount: number;
  memoryCount: number;
  edaCount: number;
  hasUserMessage: boolean;
}

const PART_TO_KEY: Record<
  string,
  "ledgerCount" | "scratchpadCount" | "taskCount" | "memoryCount" | "edaCount"
> = {
  "data-ledger-update": "ledgerCount",
  "data-scratchpad-updated": "scratchpadCount",
  "data-background-task-started": "taskCount",
  "data-memory-retrieved": "memoryCount",
  "data-eda.analysis-state": "edaCount",
  "data-eda.subset-preview": "edaCount",
  "data-eda.viz": "edaCount",
};

/**
 * Tally per-panel activity from the chat message stream so every rail icon can
 * show an "unseen update" dot consistently (not just strategy/plan).
 */
export function computeRailActivity(messages: readonly UIMessage[]): RailActivity {
  const activity: RailActivity = {
    ledgerCount: 0,
    scratchpadCount: 0,
    taskCount: 0,
    memoryCount: 0,
    edaCount: 0,
    hasUserMessage: false,
  };
  for (const message of messages) {
    if (message.role === "user") activity.hasUserMessage = true;
    for (const part of message.parts) {
      const key = PART_TO_KEY[part.type];
      if (key !== undefined) activity[key] += 1;
    }
  }
  return activity;
}
