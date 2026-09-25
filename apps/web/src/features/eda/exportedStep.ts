import type { Strategy } from "@pathfinder/shared";
import { conversationResponseSchema } from "@pathfinder/shared/generated/zod/conversationResponseSchema";

import { toStrategy } from "@/lib/api/strategy";

const UNREADABLE = "The export answered with a strategy the app cannot read.";
const NO_STEP = "The export answered with no step.";

export class ExportedStepError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExportedStepError";
  }
}

export function strategyFromExportedStep(raw: unknown): Strategy {
  const parsed = conversationResponseSchema.safeParse(raw);
  if (!parsed.success) throw new ExportedStepError(UNREADABLE);
  const strategy = toStrategy(parsed.data);
  if (strategy.steps.length === 0) throw new ExportedStepError(NO_STEP);
  return strategy;
}

/** A root that feeds nothing and is not the primary root. WDK never holds one. */
function detachedRootIds(strategy: Strategy): string[] {
  const consumed = new Set<string>();
  for (const step of strategy.steps) {
    if (step.primaryInputStepId != null) consumed.add(step.primaryInputStepId);
    if (step.secondaryInputStepId != null) consumed.add(step.secondaryInputStepId);
  }
  return strategy.steps
    .filter((step) => step.id !== strategy.rootStepId && !consumed.has(step.id))
    .map((step) => step.id);
}

export type ExportedStepPlacement =
  | { kind: "begins-strategy"; stepId: string }
  | { kind: "detached-draft"; stepId: string };

/** Where the exported step landed: it began the strategy, or it is a draft
 * root beside one that already exists. */
export function exportedStepPlacement(strategy: Strategy): ExportedStepPlacement {
  const detached = detachedRootIds(strategy);
  const draft = detached[detached.length - 1];
  if (draft !== undefined) return { kind: "detached-draft", stepId: draft };
  const root = strategy.rootStepId;
  if (root == null) throw new ExportedStepError(NO_STEP);
  return { kind: "begins-strategy", stepId: root };
}

/** How many genes of a volcano cut the exported step lacks, because the site's
 * annotation does not hold them, or null when it lacks none or a count is unknown. */
export function unmatchedGenesSentence(
  selected: number | null,
  exported: number | null | undefined,
  siteName: string,
): string | null {
  if (selected === null || exported == null || exported >= selected) return null;
  const missing = selected - exported;
  const verb = missing === 1 ? "is not a gene" : "are not genes";
  return `${String(missing)} of ${String(selected)} genes ${verb} of ${siteName}'s current annotation.`;
}
