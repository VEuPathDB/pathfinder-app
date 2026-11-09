import { leadUsagePayloadSchema } from "@pathfinder/shared/generated/zod/leadUsagePayloadSchema";
import type { UIMessage } from "ai";

export interface ContextFill {
  tokens: number;
  window: number;
}

export function leadContextFill(
  parts: readonly UIMessage["parts"][number][],
): ContextFill | null {
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    if (part?.type !== "data-lead-usage" || !("data" in part)) continue;
    const parsed = leadUsagePayloadSchema.safeParse(part.data);
    if (!parsed.success) continue;
    const tokens = parsed.data.contextTokens ?? 0;
    const window = parsed.data.contextWindow ?? 0;
    return tokens > 0 && window > 0 ? { tokens, window } : null;
  }
  return null;
}
