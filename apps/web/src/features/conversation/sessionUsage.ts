import type { UIMessage } from "ai";

interface SessionUsage {
  leadTokens: number;
  leadCost: number;
  subTokens: number;
  subCost: number;
  totalTokens: number;
  totalCost: number;
}

function isPart(part: { type: string; name?: string }, kind: string): boolean {
  return part.type === `data-${kind}` || (part.type === "data" && part.name === kind);
}

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Whole-session usage, summed from the persisted per-message parts:
 * each assistant turn's lead-usage (one merged part) plus every sub-agent
 * call's tokens/cost. Updates live as the current turn streams.
 */
export function aggregateSessionUsage(messages: readonly UIMessage[]): SessionUsage {
  let leadTokens = 0;
  let leadCost = 0;
  let subTokens = 0;
  let subCost = 0;

  for (const message of messages) {
    if (message.role !== "assistant") continue;
    let turnLeadTokens = 0;
    let turnLeadCost = 0;
    let hasLead = false;
    for (const part of message.parts) {
      if (isPart(part, "lead-usage")) {
        const data = (part as { data?: { tokens?: unknown; costUsd?: unknown } }).data;
        turnLeadTokens = num(data?.tokens);
        turnLeadCost = num(data?.costUsd);
        hasLead = true;
      } else if (isPart(part, "sub-agent-call")) {
        const data = (part as { data?: { tokens?: unknown; costUsd?: unknown } }).data;
        subTokens += num(data?.tokens);
        subCost += num(data?.costUsd);
      }
    }
    if (hasLead) {
      leadTokens += turnLeadTokens;
      leadCost += turnLeadCost;
    }
  }

  return {
    leadTokens,
    leadCost,
    subTokens,
    subCost,
    totalTokens: leadTokens + subTokens,
    totalCost: leadCost + subCost,
  };
}
