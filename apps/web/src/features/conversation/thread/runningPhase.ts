import { z } from "zod";

import type { StructuralPart } from "@/features/conversation/parts";

const dispatchSchema = z.object({
  toolCallId: z.string().min(1),
  phase: z.string().min(1),
  state: z.string().min(1),
});

function isDispatch(part: StructuralPart): boolean {
  return (
    part.type === "data-sub-agent-call" ||
    (part.type === "data" && part.name === "sub-agent-call")
  );
}

/**
 * The phase of the dispatch a turn still has open, or null when none is.
 * Read from the same chunks the trace reads, so a status line and a trace
 * group can never name different phases.
 */
export function runningPhase(parts: readonly StructuralPart[]): string | null {
  const open = new Map<string, string>();
  for (const part of parts) {
    if (!isDispatch(part)) continue;
    const parsed = dispatchSchema.safeParse(part.data);
    if (!parsed.success) continue;
    const { toolCallId, phase, state } = parsed.data;
    if (state === "started") open.set(toolCallId, phase);
    else open.delete(toolCallId);
  }
  const phases = [...open.values()];
  return phases[phases.length - 1] ?? null;
}
