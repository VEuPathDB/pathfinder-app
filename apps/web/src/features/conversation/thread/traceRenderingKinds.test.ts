import { describe, expect, it } from "vitest";

import { traceRenderingKinds } from "./traceRenderingKinds";

describe("traceRenderingKinds", () => {
  it("hoists every science part a run produced", () => {
    const kinds = traceRenderingKinds();
    for (const kind of [
      "data-eda.analysis-state",
      "data-eda.subset-preview",
      "data-eda.viz",
      "data-enrichment-results",
      "data-control-test-results",
      "data-strategy-link",
      "data-gene-set",
    ]) {
      expect(kinds.has(kind)).toBe(true);
    }
  });

  it("hoists neither the turn notices nor the durable task", () => {
    const kinds = traceRenderingKinds();
    expect(kinds.has("data-turn-failed")).toBe(false);
    expect(kinds.has("data-turn-stopped")).toBe(false);
    expect(kinds.has("data-background-task-started")).toBe(false);
  });

  it("leaves out every kind that draws nothing", () => {
    const kinds = traceRenderingKinds();
    for (const kind of [
      "data-tool-summary",
      "data-sub-agent-step",
      "data-task-progress",
      "data-task-completed",
      "data-turn-usage",
      "data-turn-status",
      "data-lead-usage",
      "data-scratchpad-updated",
      "data-ledger-update",
      "data-strategy-revision",
      "data-user-question-answers",
    ]) {
      expect(kinds.has(kind)).toBe(false);
    }
  });
});
