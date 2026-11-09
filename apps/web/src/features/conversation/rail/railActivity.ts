import type { UIMessage } from "ai";

export interface RailActivity {
  reviewCount: number;
  studyCount: number;
  hasUserMessage: boolean;
}

const PART_TO_KEY: Record<string, "reviewCount" | "studyCount"> = {
  "data-ledger-update": "reviewCount",
  "data-evidence-card": "reviewCount",
  "data-background-task-started": "reviewCount",
  "data-scratchpad-updated": "reviewCount",
  "data-memory-retrieved": "reviewCount",
  "data-eda.analysis-state": "studyCount",
  "data-eda.subset-preview": "studyCount",
  "data-eda.viz": "studyCount",
};

export function computeRailActivity(messages: readonly UIMessage[]): RailActivity {
  const activity: RailActivity = {
    reviewCount: 0,
    studyCount: 0,
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
