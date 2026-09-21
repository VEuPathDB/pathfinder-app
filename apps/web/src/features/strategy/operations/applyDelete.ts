import type { Strategy } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";
import { findParent, walkSubtreeIds } from "./utils";
import { patchSteps } from "./_patch";
import type { GraphOperation } from "@/lib/types/graphOperation";
import type { ApplyResult } from "./types";

type DeleteStepOp = Extract<GraphOperation, { kind: "deleteStep" }>;
type ParentInfo = NonNullable<ReturnType<typeof findParent>>;

export function applyDeleteStep(strategy: Strategy, op: DeleteStepOp): ApplyResult {
  const target = strategy.steps.find((s) => s.id === op.stepId);
  if (!target) return { kind: "rejected", reason: `Step ${op.stepId} not found` };
  const parentInfo = findParent(strategy.steps, op.stepId);

  switch (op.resolution) {
    case "delete-strategy":
      return {
        kind: "applied",
        next: { ...strategy, steps: [] },
        description: "Deleted strategy",
      };
    case "delete-subtree":
      return parentInfo === null
        ? dropBranch(strategy, op.stepId)
        : collapseIntoTheParent(strategy, op.stepId, parentInfo);
    case "collapse-combine":
      return parentInfo === null
        ? promotePrimary(strategy, op.stepId, target, null)
        : collapseIntoTheParent(strategy, op.stepId, parentInfo);
    case "orphan-sibling":
      return orphanSibling(strategy, op.stepId, parentInfo);
    case "promote-primary":
      return promotePrimary(strategy, op.stepId, target, parentInfo);
  }
}

function dropBranch(strategy: Strategy, stepId: string): ApplyResult {
  const subtree = new Set(walkSubtreeIds(strategy.steps, stepId));
  return {
    kind: "applied",
    next: { ...strategy, steps: strategy.steps.filter((s) => !subtree.has(s.id)) },
    description: `Deleted ${stepId} and its subtree`,
  };
}

// The branch goes, and the step that read it goes with it: a transform with no
// input reads nothing and a combine with one branch combines nothing. A
// combine's other branch takes the place the parent held.
function collapseIntoTheParent(
  strategy: Strategy,
  stepId: string,
  parentInfo: ParentInfo,
): ApplyResult {
  const { parent, slot } = parentInfo;
  const siblingId =
    inferStepKind(parent) === "combine"
      ? slot === "primary"
        ? parent.secondaryInputStepId
        : parent.primaryInputStepId
      : null;
  const drop = new Set<string>([...walkSubtreeIds(strategy.steps, stepId), parent.id]);
  let next = strategy.steps.filter((s) => !drop.has(s.id));
  const grandparent = findParent(strategy.steps, parent.id);
  if (grandparent !== null) {
    const slotKey =
      grandparent.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    next = patchSteps(next, grandparent.parent.id, { [slotKey]: siblingId ?? null });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: next },
    description: `Collapsed ${parent.id}`,
  };
}

function orphanSibling(
  strategy: Strategy,
  stepId: string,
  parentInfo: ParentInfo | null,
): ApplyResult {
  if (parentInfo === null)
    return {
      kind: "rejected",
      reason: `${stepId} is a root, so no step above it keeps another branch`,
    };
  const { parent } = parentInfo;
  const subtree = new Set(walkSubtreeIds(strategy.steps, stepId));
  let next = strategy.steps.filter((s) => !subtree.has(s.id));

  // Mirrors the backend: a secondary input with no primary breaks the node
  // invariant, so clearing the primary slot promotes the survivor instead of
  // stranding it. Diverging here would make the optimistic graph flicker into
  // a different shape than the one the server returns.
  next =
    parentInfo.slot === "primary" && parent.secondaryInputStepId != null
      ? patchSteps(next, parent.id, {
          primaryInputStepId: parent.secondaryInputStepId,
          secondaryInputStepId: null,
          operator: null,
        })
      : patchSteps(next, parent.id, {
          [parentInfo.slot === "primary"
            ? "primaryInputStepId"
            : "secondaryInputStepId"]: null,
          operator: null,
        });

  const grandparent = findParent(strategy.steps, parent.id);
  if (grandparent !== null) {
    next =
      grandparent.slot === "primary" && grandparent.parent.secondaryInputStepId != null
        ? patchSteps(next, grandparent.parent.id, {
            primaryInputStepId: grandparent.parent.secondaryInputStepId,
            secondaryInputStepId: null,
            operator: null,
          })
        : patchSteps(next, grandparent.parent.id, {
            [grandparent.slot === "primary"
              ? "primaryInputStepId"
              : "secondaryInputStepId"]: null,
          });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: next },
    description: `Deleted ${stepId}, orphaned ${parentInfo.parent.id}`,
  };
}

// The step goes and the step it reads stands where it stood. This is the
// re-wiring WDK performs when a strategy loses its root.
function promotePrimary(
  strategy: Strategy,
  stepId: string,
  target: Strategy["steps"][number],
  parentInfo: ParentInfo | null,
): ApplyResult {
  const primaryId = target.primaryInputStepId;
  if (primaryId == null || primaryId === "")
    return {
      kind: "rejected",
      reason: `${stepId} reads no step that can take its place`,
    };
  const sec = target.secondaryInputStepId;
  const secondaryDrop =
    sec != null && sec !== "" ? walkSubtreeIds(strategy.steps, sec) : [];
  const drop = new Set<string>([stepId, ...secondaryDrop]);
  let next = strategy.steps.filter((s) => !drop.has(s.id));
  if (parentInfo !== null) {
    const slotKey =
      parentInfo.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    next = patchSteps(next, parentInfo.parent.id, { [slotKey]: primaryId });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: next },
    description: `Promoted primary of ${stepId}`,
  };
}
