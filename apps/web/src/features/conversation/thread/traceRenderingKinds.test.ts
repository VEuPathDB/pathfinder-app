import { describe, expect, it } from "vitest";

import { APPENDIX_KINDS } from "../content/appendixParts";
import { traceRenderingKinds } from "./traceRenderingKinds";

describe("traceRenderingKinds", () => {
  it("hoists every science part a run produced", () => {
    const kinds = traceRenderingKinds();
    for (const kind of [
      "data-eda.viz",
      "data-eda.pca",
      "data-eda.statistics",
      "data-gene-set",
      "data-gene-set-list",
      "data-variant-comparison",
      "data-separation-result",
    ]) {
      expect(kinds.has(kind)).toBe(true);
    }
  });

  it("hoists none of the parts the turn appendix draws", () => {
    const kinds = traceRenderingKinds();
    for (const kind of APPENDIX_KINDS) {
      expect(kinds.has(kind)).toBe(false);
    }
  });

  it("hoists neither the turn notices nor the durable task", () => {
    const kinds = traceRenderingKinds();
    expect(kinds.has("data-turn-failed")).toBe(false);
    expect(kinds.has("data-turn-stopped")).toBe(false);
    expect(kinds.has("data-turn-withdrawn")).toBe(false);
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
      "data-delete-cascade",
      "data-user-question-answers",
    ]) {
      expect(kinds.has(kind)).toBe(false);
    }
  });
});
