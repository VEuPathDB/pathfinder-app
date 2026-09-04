import type { Step, Strategy } from "@pathfinder/shared";
import { findParent } from "./utils";
import { patchSteps } from "./_patch";
import type { GraphOperation } from "@/lib/types/graphOperation";
import type { ApplyResult } from "./types";

type AddLeafOp = Extract<GraphOperation, { kind: "addLeaf" }>;
type AddCombineOp = Extract<GraphOperation, { kind: "addCombine" }>;
type AddTransformOp = Extract<GraphOperation, { kind: "addTransform" }>;
type DuplicateStepOp = Extract<GraphOperation, { kind: "duplicateStep" }>;

export function applyAddLeaf(strategy: Strategy, op: AddLeafOp): ApplyResult {
  const attach = op.attach;
  if (attach.mode === "new-root") {
    return {
      kind: "applied",
      next: { ...strategy, steps: [...strategy.steps, op.step] },
      description: `Added ${op.step.displayName ?? op.step.id}`,
    };
  }
  const targetExists = strategy.steps.some((s) => s.id === attach.targetStepId);
  if (!targetExists) return { kind: "rejected", reason: "Target step not found" };
  const slotKey =
    attach.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
  return {
    kind: "applied",
    next: {
      ...strategy,
      steps: patchSteps([...strategy.steps, op.step], attach.targetStepId, {
        [slotKey]: op.step.id,
      }),
    },
    description: `Added ${op.step.displayName ?? op.step.id}`,
  };
}

export function applyAddCombine(strategy: Strategy, op: AddCombineOp): ApplyResult {
  if (op.leftId === op.rightId)
    return { kind: "rejected", reason: "Combine inputs must differ" };
  if (
    !strategy.steps.some((s) => s.id === op.leftId) ||
    !strategy.steps.some((s) => s.id === op.rightId)
  ) {
    return { kind: "rejected", reason: "Combine input step missing" };
  }
  const combine: Step = {
    ...op.step,
    primaryInputStepId: op.leftId,
    secondaryInputStepId: op.rightId,
  };
  return {
    kind: "applied",
    next: { ...strategy, steps: [...strategy.steps, combine] },
    description: `Combined ${op.leftId} and ${op.rightId}`,
  };
}

export function applyAddTransform(strategy: Strategy, op: AddTransformOp): ApplyResult {
  if (op.mode === "new-root") {
    return {
      kind: "applied",
      next: { ...strategy, steps: [...strategy.steps, op.step] },
      description: `Added transform ${op.step.displayName ?? op.step.id}`,
    };
  }
  const consumer = findParent(strategy.steps, op.inputId);
  const transform: Step = { ...op.step, primaryInputStepId: op.inputId };
  let nextSteps = [...strategy.steps, transform];
  if (consumer !== null) {
    const slotKey =
      consumer.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    nextSteps = patchSteps(nextSteps, consumer.parent.id, {
      [slotKey]: transform.id,
    });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: nextSteps },
    description: `Inserted transform ${op.step.displayName ?? op.step.id}`,
  };
}

export function applyDuplicateStep(
  strategy: Strategy,
  op: DuplicateStepOp,
): ApplyResult {
  const source = strategy.steps.find((s) => s.id === op.sourceStepId);
  if (!source) return { kind: "rejected", reason: `Step ${op.sourceStepId} not found` };

  const duplicate: Step = {
    ...source,
    id: op.duplicateStepId,
    wdkStepId: null,
    estimatedSize: null,
    validation: null,
  };

  const combine: Step = {
    id: op.combineStepId,
    kind: "combine",
    displayName: op.combineDisplayName ?? "INTERSECT combine",
    operator: "INTERSECT",
    recordType: source.recordType ?? null,
    primaryInputStepId: op.sourceStepId,
    secondaryInputStepId: op.duplicateStepId,
    isFiltered: false,
  };

  const parentInfo = findParent(strategy.steps, op.sourceStepId);
  let nextSteps: Step[] = strategy.steps.map((s) => s);
  if (parentInfo !== null) {
    const slotKey =
      parentInfo.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    nextSteps = patchSteps(nextSteps, parentInfo.parent.id, {
      [slotKey]: op.combineStepId,
    });
  }
  nextSteps = [...nextSteps, duplicate, combine];

  return {
    kind: "applied",
    next: { ...strategy, steps: nextSteps },
    description: `Duplicated ${op.sourceStepId}`,
  };
}
