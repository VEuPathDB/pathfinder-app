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
  it("tallies per-panel data parts and detects a user message", () => {
    const activity = computeRailActivity([
      message("m1", "user", ["text"]),
      message("m2", "assistant", [
        "ledger-update",
        "ledger-update",
        "scratchpad-updated",
        "memory-retrieved",
        "text",
      ]),
    ]);
    expect(activity.hasUserMessage).toBe(true);
    expect(activity.ledgerCount).toBe(2);
    expect(activity.scratchpadCount).toBe(1);
    expect(activity.memoryCount).toBe(1);
    expect(activity.taskCount).toBe(0);
  });

  it("reports no user message for an empty/assistant-only thread", () => {
    const activity = computeRailActivity([
      message("m1", "assistant", ["ledger-update"]),
    ]);
    expect(activity.hasUserMessage).toBe(false);
    expect(activity.ledgerCount).toBe(1);
  });
});

describe("computeRailActivity eda", () => {
  it("counts every eda part towards the eda panel", () => {
    const activity = computeRailActivity([
      message("m1", "assistant", [
        "eda.analysis-state",
        "eda.subset-preview",
        "eda.viz",
      ]),
    ]);
    expect(activity.edaCount).toBe(3);
    expect(activity.ledgerCount).toBe(0);
  });

  it("is zero when no eda part arrived", () => {
    const activity = computeRailActivity([
      message("m1", "assistant", ["task-progress"]),
    ]);
    expect(activity.edaCount).toBe(0);
  });
});
