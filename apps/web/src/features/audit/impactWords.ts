import type { GenomeUse } from "@strategist/shared/generated/types/GenomeUse";
import type { Weighing } from "@strategist/shared/generated/types/Weighing";

import { USE_WORDS } from "./words";

export function genomeUseText(use: GenomeUse): string {
  if (use.source !== "model_role") return USE_WORDS[use.source];
  return use.reference
    ? "the reference model of its strain pair"
    : "the strain model of its strain pair";
}

export function fallbackText(weighing: Weighing): string | null {
  const unread = [
    weighing.importance.source === "not_read",
    weighing.use.source === "unknown",
  ].filter(Boolean).length;
  if (unread === 0) return null;
  return unread === 1
    ? "1 input was not read, so its lower value is used."
    : `${String(unread)} inputs were not read, so their lower values are used.`;
}
