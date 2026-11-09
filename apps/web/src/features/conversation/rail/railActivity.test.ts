import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { computeRailActivity } from "./railActivity";

function message(id: string, role: UIMessage["role"], kinds: string[]): UIMessage {
  return {
    id,
    role,
    parts: kinds.map((kind) =>
      kind === "text" ? { type: "text", text: "" } : { type: `data-${kind}`, data: {} },
    ),
  };
}

describe("computeRailActivity", () => {
  it("counts every part Review draws toward review", () => {
    const activity = computeRailActivity([
      message("m1", "user", ["text"]),
      message("m2", "assistant", [
        "ledger-update",
        "evidence-card",
        "background-task-started",
        "scratchpad-updated",
        "memory-retrieved",
        "text",
      ]),
    ]);
    expect([
      activity.hasUserMessage,
      activity.reviewCount,
      activity.studyCount,
    ]).toEqual([true, 5, 0]);
  });

  it("reports no user message for an assistant-only thread", () => {
    const activity = computeRailActivity([
      message("m1", "assistant", ["ledger-update"]),
    ]);
    expect([activity.hasUserMessage, activity.reviewCount]).toEqual([false, 1]);
  });

  it("counts every eda part toward study", () => {
    const activity = computeRailActivity([
      message("m1", "assistant", [
        "eda.analysis-state",
        "eda.subset-preview",
        "eda.viz",
        "task-progress",
      ]),
    ]);
    expect([activity.studyCount, activity.reviewCount]).toEqual([3, 0]);
  });
});
