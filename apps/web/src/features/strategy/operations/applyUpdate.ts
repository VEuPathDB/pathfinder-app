import type { Step, Strategy, StrategyStepNode } from "@pathfinder/shared";
import { patchSteps } from "./_patch";
import type { GraphOperation } from "@/lib/types/graphOperation";
import type { ApplyResult } from "./types";

type UpdateParamsOp = Extract<GraphOperation, { kind: "updateStepParams" }>;
type UpdateOpOp = Extract<GraphOperation, { kind: "updateCombineOperator" }>;
type UpdateMetaOp = Extract<GraphOperation, { kind: "updateStepMeta" }>;
type UpdateStrategyMetaOp = Extract<GraphOperation, { kind: "updateStrategyMeta" }>;
type DeleteEdgeOp = Extract<GraphOperation, { kind: "deleteEdge" }>;
type WireInputOp = Extract<GraphOperation, { kind: "wireInput" }>;
type ReplaceStrategyOp = Extract<GraphOperation, { kind: "replaceStrategy" }>;

export function applyUpdateStepParams(
  strategy: Strategy,
  op: UpdateParamsOp,
): ApplyResult {
  const target = strategy.steps.find((s) => s.id === op.stepId);
  if (target === undefined)
    return { kind: "rejected", reason: `Step ${op.stepId} not found` };
  const merged = { ...(target.parameters ?? {}), ...op.parameters };
  return {
    kind: "applied",
    next: {
      ...strategy,
      steps: patchSteps(strategy.steps, op.stepId, { parameters: merged }),
    },
    description: `Updated parameters of ${op.stepId}`,
  };
}

export function applyUpdateCombineOperator(
  strategy: Strategy,
  op: UpdateOpOp,
): ApplyResult {
  if (!strategy.steps.some((s) => s.id === op.stepId))
    return { kind: "rejected", reason: `Step ${op.stepId} not found` };
  return {
    kind: "applied",
    next: {
      ...strategy,
      steps: patchSteps(strategy.steps, op.stepId, {
        operator: op.operator,
        colocationParams: op.colocationParams ?? null,
      }),
    },
    description: `Set operator of ${op.stepId} to ${op.operator}`,
  };
}

export function applyUpdateStepMeta(strategy: Strategy, op: UpdateMetaOp): ApplyResult {
  if (!strategy.steps.some((s) => s.id === op.stepId))
    return { kind: "rejected", reason: `Step ${op.stepId} not found` };
  return {
    kind: "applied",
    next: {
      ...strategy,
      steps: patchSteps(strategy.steps, op.stepId, {
        displayName: op.displayName,
      }),
    },
    description: `Renamed ${op.stepId}`,
  };
}

export function applyUpdateStrategyMeta(
  strategy: Strategy,
  op: UpdateStrategyMetaOp,
): ApplyResult {
  const next = { ...strategy };
  if (op.name !== undefined) next.name = op.name;
  if (op.description !== undefined) next.description = op.description;
  return {
    kind: "applied",
    next,
    description: "Updated strategy metadata",
  };
}

export function applyReplaceStrategy(
  strategy: Strategy,
  op: ReplaceStrategyOp,
): ApplyResult {
  const flat = treeToFlatSteps(op.root, strategy);
  const next: Strategy = {
    ...strategy,
    steps: flat,
    rootStepId: op.root.id ?? null,
  };
  if (op.name !== undefined) next.name = op.name;
  if (op.description !== undefined) next.description = op.description;
  return {
    kind: "applied",
    next,
    description: "Replaced strategy",
  };
}

function treeToFlatSteps(root: StrategyStepNode, strategy: Strategy): Step[] {
  const existingById = new Map(strategy.steps.map((s) => [s.id, s]));
  const out: Step[] = [];
  const visit = (node: StrategyStepNode): void => {
    const primary = node.primaryInput ?? null;
    const secondary = node.secondaryInput ?? null;
    if (primary !== null) visit(primary);
    if (secondary !== null) visit(secondary);
    const nodeId = node.id ?? "";
    const existing = existingById.get(nodeId);
    const flat: Step = {
      ...(existing ?? { id: nodeId }),
      id: nodeId,
      kind:
        primary !== null && secondary !== null
          ? "combine"
          : primary !== null
            ? "transform"
            : "search",
      displayName: node.displayName ?? null,
      searchName: node.searchName,
      parameters: node.parameters ?? null,
      operator: node.operator ?? null,
      colocationParams: node.colocationParams ?? null,
      primaryInputStepId: primary?.id ?? null,
      secondaryInputStepId: secondary?.id ?? null,
    };
    out.push(flat);
  };
  visit(root);
  return out;
}

export function applyWireInput(strategy: Strategy, op: WireInputOp): ApplyResult {
  if (!strategy.steps.some((s) => s.id === op.targetStepId))
    return { kind: "rejected", reason: `Target ${op.targetStepId} not found` };
  if (!strategy.steps.some((s) => s.id === op.sourceStepId))
    return { kind: "rejected", reason: `Source ${op.sourceStepId} not found` };
  const slotKey = op.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
  return {
    kind: "applied",
    next: {
      ...strategy,
      steps: patchSteps(strategy.steps, op.targetStepId, {
        [slotKey]: op.sourceStepId,
      }),
    },
    description: `Wired ${op.sourceStepId} -> ${op.targetStepId}`,
  };
}

export function applyDeleteEdge(
  strategy: Strategy,
  op: DeleteEdgeOp,
  recurse: (s: Strategy, op: GraphOperation) => ApplyResult,
): ApplyResult {
  if (!strategy.steps.some((s) => s.id === op.targetId))
    return { kind: "rejected", reason: `Target ${op.targetId} not found` };
  if (op.resolution === "detach") {
    const slotKey =
      op.slot === "primary" ? "primaryInputStepId" : "secondaryInputStepId";
    return {
      kind: "applied",
      next: {
        ...strategy,
        steps: patchSteps(strategy.steps, op.targetId, {
          [slotKey]: null,
          operator: null,
          colocationParams: null,
        }),
      },
      description: `Detached edge ${op.sourceId} -> ${op.targetId}`,
    };
  }
  return recurse(strategy, {
    kind: "deleteStep",
    stepId: op.sourceId,
    resolution: "collapse-combine",
  });
}
