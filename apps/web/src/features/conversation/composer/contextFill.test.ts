import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { leadContextFill } from "./contextFill";

function usage(
  contextTokens: number,
  contextWindow: number,
): UIMessage["parts"][number] {
  return {
    type: "data-lead-usage",
    data: {
      modelId: "openai:gpt-5.6-luna",
      tokens: 15,
      costUsd: "0.01",
      contextTokens,
      contextWindow,
    },
  };
}

describe("leadContextFill", () => {
  it("reads the latest assistant context fill", () => {
    expect(leadContextFill([usage(1000, 100_000), usage(36_800, 1_050_000)])).toEqual({
      tokens: 36_800,
      window: 1_050_000,
    });
  });

  it("is null before the assistant reports a context", () => {
    expect(leadContextFill([{ type: "text", text: "hi" }])).toBe(null);
  });

  it("is null when the model reports no window", () => {
    expect(leadContextFill([usage(500, 0)])).toBe(null);
  });
});
