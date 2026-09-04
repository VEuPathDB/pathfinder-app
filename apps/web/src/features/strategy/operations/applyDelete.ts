import type { Strategy } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";
import { findParent, walkSubtreeIds } from "./utils";
import { patchSteps } from "./_patch";
import type { GraphOperation } from "@/lib/types/graphOperation";
import type { ApplyResult } from "./types";

type DeleteStepOp = Extract<GraphOperation, { kind: "deleteStep" }>;

export function applyDeleteStep(strategy: Strategy, op: DeleteStepOp): ApplyResult {
  const target = strategy.steps.find((s) => s.id === op.stepId);
  if (!target) return { kind: "rejected", reason: `Step ${op.stepId} not found` };

  switch (op.resolution) {
    case "delete-strategy":
      return {
        kind: "applied",
        next: { ...strategy, steps: [] },
        description: "Deleted strategy",
      };
    case "delete-subtree":
      return deleteSubtree(strategy, op.stepId);
    case "collapse-combine":
      return collapseCombine(strategy, op.stepId, target);
    case "orphan-sibling":
      return orphanSibling(strategy, op.stepId);
    case "promote-primary":
      return promotePrimary(strategy, op.stepId, target);
  }
}

function deleteSubtree(strategy: Strategy, stepId: string): ApplyResult {
  const subtree = new Set(walkSubtreeIds(strategy.steps, stepId));
  const parentInfo = findParent(strategy.steps, stepId);
  let next = strategy.steps.filter((s) => !subtree.has(s.id));
  if (parentInfo !== null && inferStepKind(parentInfo.parent) === "transform") {
    next = next.filter((s) => s.id !== parentInfo.parent.id);
    const grandparentInfo = findParent(strategy.steps, parentInfo.parent.id);
    if (grandparentInfo !== null) {
      const slotKey =
        grandparentInfo.slot === "primary"
          ? "primaryInputStepId"
          : "secondaryInputStepId";
      next = patchSteps(next, grandparentInfo.parent.id, { [slotKey]: null });
    }
  } else if (parentInfo !== null) {
    const slotKey =
      parentInfo.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    next = patchSteps(next, parentInfo.parent.id, { [slotKey]: null });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: next },
    description: `Deleted ${stepId} and its subtree`,
  };
}

function orphanSibling(strategy: Strategy, stepId: string): ApplyResult {
  const parentInfo = findParent(strategy.steps, stepId);
  if (parentInfo === null)
    return { kind: "rejected", reason: "orphan-sibling needs a combine parent" };
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

function collapseCombine(
  strategy: Strategy,
  stepId: string,
  target: Strategy["steps"][number],
): ApplyResult {
  const parentInfo = findParent(strategy.steps, stepId);
  if (parentInfo === null) {
    if (inferStepKind(target) !== "combine")
      return { kind: "rejected", reason: "collapse-combine on non-combine root" };
    const dropIds = new Set<string>([stepId]);
    const sec = target.secondaryInputStepId;
    if (sec != null && sec !== "")
      for (const id of walkSubtreeIds(strategy.steps, sec)) dropIds.add(id);
    return {
      kind: "applied",
      next: {
        ...strategy,
        steps: strategy.steps.filter((s) => !dropIds.has(s.id)),
      },
      description: `Collapsed combine ${stepId}`,
    };
  }
  const { parent, slot } = parentInfo;
  if (inferStepKind(parent) === "transform") {
    const subtree = new Set(walkSubtreeIds(strategy.steps, stepId));
    let next = strategy.steps.filter((s) => !subtree.has(s.id) && s.id !== parent.id);
    const gp = findParent(strategy.steps, parent.id);
    if (gp !== null) {
      const slotKey =
        gp.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
      next = patchSteps(next, gp.parent.id, { [slotKey]: null });
    }
    return {
      kind: "applied",
      next: { ...strategy, steps: next },
      description: `Collapsed via transform ${stepId}`,
    };
  }
  const siblingId =
    slot === "primary" ? parent.secondaryInputStepId : parent.primaryInputStepId;
  const drop = new Set<string>([...walkSubtreeIds(strategy.steps, stepId), parent.id]);
  const grandparent = findParent(strategy.steps, parent.id);
  let next = strategy.steps.filter((s) => !drop.has(s.id));
  if (grandparent !== null) {
    const slotKey =
      grandparent.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    next = patchSteps(next, grandparent.parent.id, {
      [slotKey]: siblingId ?? null,
    });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: next },
    description: `Collapsed combine ${parent.id}`,
  };
}

function promotePrimary(
  strategy: Strategy,
  stepId: string,
  target: Strategy["steps"][number],
): ApplyResult {
  if (inferStepKind(target) !== "combine")
    return { kind: "rejected", reason: "promote-primary on non-combine" };
  const sec = target.secondaryInputStepId;
  const secondaryDrop =
    sec != null && sec !== "" ? walkSubtreeIds(strategy.steps, sec) : [];
  const drop = new Set<string>([stepId, ...secondaryDrop]);
  const parentInfo = findParent(strategy.steps, stepId);
  let next = strategy.steps.filter((s) => !drop.has(s.id));
  if (parentInfo !== null) {
    const slotKey =
      parentInfo.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    next = patchSteps(next, parentInfo.parent.id, {
      [slotKey]: target.primaryInputStepId ?? null,
    });
  }
  return {
    kind: "applied",
    next: { ...strategy, steps: next },
    description: `Promoted primary of ${stepId}`,
  };
}
