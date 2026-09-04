import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { aggregateSessionUsage } from "./sessionUsage";

function assistant(parts: unknown[]): UIMessage {
  return {
    id: Math.random().toString(),
    role: "assistant",
    parts,
  } as unknown as UIMessage;
}

describe("aggregateSessionUsage", () => {
  it("sums lead + sub-agent usage across the whole session", () => {
    const messages = [
      assistant([
        { type: "data-lead-usage", data: { tokens: 1000, costUsd: "0.01" } },
        { type: "data-sub-agent-call", data: { tokens: 500, costUsd: "0.002" } },
        { type: "data-sub-agent-call", data: { tokens: 300, costUsd: "0.001" } },
      ]),
      assistant([
        { type: "data-lead-usage", data: { tokens: 2000, costUsd: "0.02" } },
        { type: "data-sub-agent-call", data: { tokens: 700, costUsd: "0.003" } },
      ]),
    ];
    const usage = aggregateSessionUsage(messages);
    expect(usage.leadTokens).toBe(3000);
    expect(usage.subTokens).toBe(1500);
    expect(usage.totalTokens).toBe(4500);
    expect(usage.leadCost).toBeCloseTo(0.03);
    expect(usage.subCost).toBeCloseTo(0.006);
    expect(usage.totalCost).toBeCloseTo(0.036);
  });

  it("takes the latest (merged) lead-usage per message, not the sum", () => {
    const messages = [
      assistant([
        { type: "data-lead-usage", data: { tokens: 50, costUsd: "0.001" } },
        { type: "data-lead-usage", data: { tokens: 120, costUsd: "0.004" } },
      ]),
    ];
    expect(aggregateSessionUsage(messages).leadTokens).toBe(120);
  });

  it("returns zeros when there is no usage", () => {
    const usage = aggregateSessionUsage([assistant([{ type: "text", text: "hi" }])]);
    expect(usage.totalTokens).toBe(0);
    expect(usage.totalCost).toBe(0);
  });
});
