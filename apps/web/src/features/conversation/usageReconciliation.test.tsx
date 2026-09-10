/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import type { UIMessage } from "ai";
import {
  reduceSnapshot,
  threadUsage,
  type MessagePart,
} from "@veupathdb/assistant-client";
import type { DataLeadUsagePayload, DataSubAgentCallPayload } from "@pathfinder/shared";

import type { TraceUsageView } from "@/features/conversation/thread/Trace";
import { formatCost, formatTokens } from "@/features/conversation/usageFormat";
import recordedTurn from "./__fixtures__/recordedTurn.json";

import { turnUsageOf } from "./thread/TraceAnchor";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() },
  Toaster: () => null,
}));

/** The recorded turn's lead usage, as the wire reported it. */
const RECORDED_LEAD_TOKENS = 41_800;
const RECORDED_LEAD_COST = 0.0131;
/** The recorded turn's one dispatch, merged to its completed state. */
const RECORDED_SUB_TOKENS = 12_300;
const RECORDED_SUB_COST = 0.004;

function recordedParts(): MessagePart[] {
  const assistant = reduceSnapshot(recordedTurn as unknown[]).find(
    (message) => message.role === "assistant",
  );
  if (assistant === undefined) throw new Error("the recorded turn holds no message");
  return assistant.parts;
}

function assistantMessage(id: string, parts: MessagePart[]): UIMessage {
  return { id, role: "assistant", parts };
}

function leadUsagePart(payload: DataLeadUsagePayload): MessagePart {
  return { type: "data-lead-usage", id: "lead-usage", data: payload };
}

function dispatchPart(payload: DataSubAgentCallPayload): MessagePart {
  return { type: "data-sub-agent-call", id: payload.toolCallId, data: payload };
}

/** The per-turn chip's numbers. The chip draws nothing without lead usage. */
function chipUsage(parts: MessagePart[]): TraceUsageView {
  const usage = turnUsageOf(parts);
  if (usage === null) throw new Error("the parts carry no lead usage");
  return usage;
}

/** A second turn: one lead usage and two dispatches. */
function secondTurnParts(): MessagePart[] {
  return [
    dispatchPart({
      toolCallId: "sa_20",
      subAgent: "build_strategy",
      phase: "execution",
      state: "completed",
      modelId: "openai:gpt-5.6-luna",
      tokens: 1_200,
      costUsd: "0.01",
    }),
    dispatchPart({
      toolCallId: "sa_21",
      subAgent: "verify_strategy",
      phase: "verification",
      state: "completed",
      modelId: "openai:gpt-5.6-luna",
      tokens: 800,
      costUsd: "0.004",
    }),
    leadUsagePart({
      modelId: "openai:gpt-5.6-luna",
      tokens: 3_000,
      costUsd: "0.05",
    }),
  ];
}

/**
 * A dispatch that died on its token ceiling: the wire leaves its state at
 * "started" and still reports the tokens it spent.
 */
function budgetStoppedParts(): MessagePart[] {
  return [
    dispatchPart({
      toolCallId: "sa_30",
      subAgent: "frame_problem",
      phase: "frame",
      state: "started",
      modelId: "openai:gpt-5.6-luna",
      tokens: 7_000,
      costUsd: "0.003",
    }),
    leadUsagePart({
      modelId: "openai:gpt-5.6-luna",
      tokens: RECORDED_LEAD_TOKENS,
      costUsd: String(RECORDED_LEAD_COST),
    }),
  ];
}

describe("usage reconciliation", () => {
  it("reads one message's parts to the same tokens and cost on both surfaces", () => {
    const parts = recordedParts();
    const chip = chipUsage(parts);
    const footer = threadUsage([assistantMessage("m1", parts)]);

    expect(chip.tokens).toBe(RECORDED_LEAD_TOKENS + RECORDED_SUB_TOKENS);
    expect(footer.total.tokens).toBe(chip.tokens);
    expect(Number(chip.costUsd)).toBe(footer.total.costUsd);
    expect(footer.total.costUsd).toBeCloseTo(
      RECORDED_LEAD_COST + RECORDED_SUB_COST,
      12,
    );
  });

  it("splits the same message into the footer's lead and sub-agent halves", () => {
    const footer = threadUsage([assistantMessage("m1", recordedParts())]);
    expect(footer.lead.tokens).toBe(RECORDED_LEAD_TOKENS);
    expect(footer.subAgents.tokens).toBe(RECORDED_SUB_TOKENS);
    expect(footer.lead.costUsd).toBeCloseTo(RECORDED_LEAD_COST, 12);
    expect(footer.subAgents.costUsd).toBeCloseTo(RECORDED_SUB_COST, 12);
  });

  it("prints the same formatted token and cost strings on both surfaces", () => {
    const parts = recordedParts();
    const chip = chipUsage(parts);
    const footer = threadUsage([assistantMessage("m1", parts)]);

    expect(formatTokens(chip.tokens)).toBe(formatTokens(footer.total.tokens));
    expect(formatCost(Number(chip.costUsd))).toBe(formatCost(footer.total.costUsd));
    expect(formatTokens(chip.tokens)).toBe("54.1K");
  });

  it("sums the two turns' chips into the footer's conversation total", () => {
    const first = recordedParts();
    const second = secondTurnParts();
    const firstChip = chipUsage(first);
    const secondChip = chipUsage(second);
    const footer = threadUsage([
      assistantMessage("m1", first),
      assistantMessage("m2", second),
    ]);

    expect(secondChip.tokens).toBe(5_000);
    expect(firstChip.tokens + secondChip.tokens).toBe(59_100);
    expect(footer.total.tokens).toBe(firstChip.tokens + secondChip.tokens);
    expect(footer.total.costUsd).toBeCloseTo(
      Number(firstChip.costUsd) + Number(secondChip.costUsd),
      12,
    );
  });

  it("counts a dispatch stopped on its token ceiling on both surfaces", () => {
    const parts = budgetStoppedParts();
    const chip = chipUsage(parts);
    const footer = threadUsage([assistantMessage("m1", parts)]);

    expect(chip.tokens).toBe(RECORDED_LEAD_TOKENS + 7_000);
    expect(chip.tokens).toBeGreaterThan(RECORDED_LEAD_TOKENS);
    expect(footer.subAgents.tokens).toBe(7_000);
    expect(footer.total.tokens).toBe(chip.tokens);
    expect(Number(chip.costUsd)).toBe(footer.total.costUsd);
  });
});
