import type { UIMessage } from "ai";
import {
  isDataPart,
  isToolPart,
  readSubAgentStep,
  runningPhase,
  threadUsage,
  turnUsage,
  type MessagePart,
} from "@veupathdb/assistant-client";
import { toTraceParts } from "@veupathdb/assistant-client/ai-sdk";
import { describe, expect, it } from "vitest";

import { protocolPart } from "./parts";

type UIPart = UIMessage["parts"][number];

function assistant(parts: MessagePart[]): UIMessage {
  return { id: "m1", role: "assistant", parts };
}

describe("toTraceParts", () => {
  it("keeps the parts the protocol defines and drops the rest", () => {
    const parts: UIPart[] = [
      { type: "text", text: "the count is 42" },
      { type: "step-start" },
      { type: "custom", kind: "acme.widget" },
      { type: "reasoning-file", mediaType: "text/plain", url: "data:," },
      {
        type: "dynamic-tool",
        toolName: "whatever",
        toolCallId: "call_2",
        state: "input-available",
        input: {},
      },
    ];

    expect(toTraceParts(parts)).toEqual([
      { type: "text", text: "the count is 42" },
      { type: "step-start" },
    ]);
  });

  it("folds the line a tool wrote onto its own call", () => {
    const call = {
      type: "tool-run_control_tests_on_step",
      toolCallId: "call_1",
      state: "output-available",
      input: { stepId: 7 },
      output: { mcc: 0.81 },
      summary: "MCC 0.81 on 132 genes",
      summaryStatus: "ok",
    } as unknown as UIPart;

    expect(toTraceParts([call])).toEqual([
      {
        type: "tool-run_control_tests_on_step",
        toolCallId: "call_1",
        state: "output-available",
        input: { stepId: 7 },
        output: { mcc: 0.81 },
        summary: "MCC 0.81 on 132 genes",
        summaryStatus: "ok",
      },
    ]);
  });
});

describe("runningPhase over this app's part shapes", () => {
  it("names the phase whose dispatch is still open", () => {
    const parts = [
      {
        type: "data-sub-agent-call",
        data: { toolCallId: "c1", phase: "frame", state: "started" },
      },
      {
        type: "data-sub-agent-call",
        data: { toolCallId: "c1", phase: "frame", state: "completed" },
      },
      {
        type: "data-sub-agent-call",
        data: { toolCallId: "c2", phase: "build", state: "started" },
      },
    ];

    expect(runningPhase(parts)).toBe("build");
  });

  it("reads an assistant-ui data part once the normalizer names its kind", () => {
    const part = {
      type: "data",
      name: "sub-agent-call",
      data: { toolCallId: "c1", phase: "verification", state: "started" },
    };

    expect(runningPhase([part])).toBe(null);
    expect(runningPhase([protocolPart(part)])).toBe("verification");
  });
});

describe("turnUsage and threadUsage", () => {
  it("sums the lead's own usage and every dispatch it made", () => {
    const usage = turnUsage([
      {
        type: "data-lead-usage",
        data: { tokens: 1000, costUsd: "0.01", modelId: "openai:m" },
      },
      { type: "data-sub-agent-call", data: { tokens: 500, costUsd: "0.002" } },
      { type: "data-sub-agent-call", data: { tokens: 300, costUsd: "0.001" } },
    ]);

    expect(usage.lead).toEqual({ tokens: 1000, costUsd: 0.01 });
    expect(usage.modelId).toBe("openai:m");
    expect(usage.subAgents.tokens).toBe(800);
    expect(usage.total.tokens).toBe(1800);
    expect(usage.total.costUsd).toBeCloseTo(0.013, 12);
  });

  it("takes the last lead-usage part of a turn, which is the merged one", () => {
    const usage = turnUsage([
      { type: "data-lead-usage", data: { tokens: 50, costUsd: "0.001" } },
      { type: "data-lead-usage", data: { tokens: 120, costUsd: "0.004" } },
    ]);

    expect(usage.lead).toEqual({ tokens: 120, costUsd: 0.004 });
  });

  it("counts nothing for a payload whose fields carry the wrong type", () => {
    const usage = turnUsage([
      { type: "data-lead-usage", data: { tokens: "1000", costUsd: 0.01 } },
    ]);

    expect(usage.lead).toEqual({ tokens: 0, costUsd: 0 });
    expect(usage.total).toEqual({ tokens: 0, costUsd: 0 });
  });

  it("sums the assistant's turns and leaves the user's messages out", () => {
    const usage = threadUsage([
      assistant([
        { type: "data-lead-usage", data: { tokens: 1000, costUsd: "0.01" } },
        { type: "data-sub-agent-call", data: { tokens: 500, costUsd: "0.002" } },
      ]),
      assistant([{ type: "data-lead-usage", data: { tokens: 2000, costUsd: "0.02" } }]),
      { id: "u1", role: "user", parts: [{ type: "text", text: "hi" }] } as UIMessage,
    ]);

    expect(usage.lead.tokens).toBe(3000);
    expect(usage.subAgents.tokens).toBe(500);
    expect(usage.total.tokens).toBe(3500);
    expect(usage.total.costUsd).toBeCloseTo(0.032, 12);
  });
});

describe("the part readers the trace and the exhibits use", () => {
  it("tells a tool call from a data part", () => {
    const call: MessagePart = {
      type: "tool-run_control_tests_on_step",
      toolCallId: "call_1",
      state: "input-available",
      input: {},
    };
    const data: MessagePart = { type: "data-sub-agent-call", data: {} };

    expect(isToolPart(call)).toBe(true);
    expect(isToolPart(data)).toBe(false);
    expect(isDataPart(data)).toBe(true);
    expect(isDataPart(call)).toBe(false);
  });

  it("reads a sub-agent step and refuses one that names no parent", () => {
    const step = readSubAgentStep({
      parentToolCallId: "call_parent",
      kind: "tool",
      state: "completed",
      toolCallId: "call_inner",
      resultSummary: "132 genes",
    });

    expect(step?.toolCallId).toBe("call_inner");
    expect(step?.resultSummary).toBe("132 genes");
    expect(readSubAgentStep({ kind: "tool", state: "completed" })).toBe(undefined);
  });
});
