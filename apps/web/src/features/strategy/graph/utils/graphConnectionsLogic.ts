import type { Connection } from "@xyflow/react";
import type { Step } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";
import { resolveRecordType } from "@/features/strategy/graph";

type GraphIndices = {
  stepsById: Map<string, Step>;
  usedAsInputCount: Map<string, number>;
  rootIds: string[];
  rootSet: Set<string>;
};

export function buildGraphIndices(steps: Step[]): GraphIndices {
  const stepsById = new Map<string, Step>();
  const usedAsInputCount = new Map<string, number>();
  for (const step of steps) {
    stepsById.set(step.id, step);
  }
  for (const step of steps) {
    if (step.primaryInputStepId != null && step.primaryInputStepId !== "") {
      usedAsInputCount.set(
        step.primaryInputStepId,
        (usedAsInputCount.get(step.primaryInputStepId) ?? 0) + 1,
      );
    }
    if (step.secondaryInputStepId != null && step.secondaryInputStepId !== "") {
      usedAsInputCount.set(
        step.secondaryInputStepId,
        (usedAsInputCount.get(step.secondaryInputStepId) ?? 0) + 1,
      );
    }
  }
  const rootIds = steps
    .map((s) => s.id)
    .filter((id) => (usedAsInputCount.get(id) ?? 0) === 0);
  return {
    stepsById,
    usedAsInputCount,
    rootIds,
    rootSet: new Set(rootIds),
  };
}

export function isUpstream(
  sourceId: string,
  maybeUpstreamId: string,
  stepsById: Map<string, Step>,
) {
  // Walk upstream pointers (inputs) starting from sourceId.
  const visited = new Set<string>();
  const stack = [sourceId];
  while (stack.length) {
    const current = stack.pop()!;
    if (current === maybeUpstreamId) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    const step = stepsById.get(current);
    if (!step) continue;
    if (step.primaryInputStepId != null && step.primaryInputStepId !== "")
      stack.push(step.primaryInputStepId);
    if (step.secondaryInputStepId != null && step.secondaryInputStepId !== "")
      stack.push(step.secondaryInputStepId);
  }
  return false;
}

export function isValidGraphConnection(connection: Connection, indices: GraphIndices) {
  const sourceId = connection.source;
  const targetId = connection.target;
  if (sourceId === "" || targetId === "") return false;
  if (sourceId === targetId) return false;

  const sourceStep = indices.stepsById.get(sourceId);
  const targetStep = indices.stepsById.get(targetId);
  if (!sourceStep || !targetStep) return false;

  // Once a step's output is connected (used as input), it cannot be reused.
  const sourceIsRoot = indices.rootSet.has(sourceId);
  if (!sourceIsRoot) return false;

  if (connection.targetHandle === "left") {
    const kind = inferStepKind(targetStep);
    if (kind !== "transform" && kind !== "combine") return false;
    if (targetStep.primaryInputStepId != null && targetStep.primaryInputStepId !== "")
      return false;
    if (isUpstream(sourceId, targetId, indices.stepsById)) return false;
    return true;
  }
  if (connection.targetHandle === "left-secondary") {
    const kind = inferStepKind(targetStep);
    if (kind !== "combine") return false;
    if (
      targetStep.secondaryInputStepId != null &&
      targetStep.secondaryInputStepId !== ""
    )
      return false;
    if (isUpstream(sourceId, targetId, indices.stepsById)) return false;
    return true;
  }

  // Otherwise treat as "combine two outputs" gesture.
  // Only possible/meaningful when the graph has multiple outputs (roots).
  if (indices.rootIds.length === 1) return false;
  if (!indices.rootSet.has(targetId)) return false;
  return true;
}

type ConnectionEffect =
  | { type: "patch"; targetId: string; patch: Partial<Step> }
  | { type: "pendingCombine"; sourceId: string; targetId: string }
  | { type: "noop" };

export function getConnectionEffect(
  connection: Connection,
  indices: GraphIndices,
): ConnectionEffect {
  if (!isValidGraphConnection(connection, indices)) return { type: "noop" };
  const sourceId = connection.source;
  const targetId = connection.target;

  if (connection.targetHandle === "left") {
    return { type: "patch", targetId, patch: { primaryInputStepId: sourceId } };
  }
  if (connection.targetHandle === "left-secondary") {
    return { type: "patch", targetId, patch: { secondaryInputStepId: sourceId } };
  }
  return { type: "pendingCombine", sourceId, targetId };
}

export function inferCombineRecordTypeOrMismatch(args: {
  sourceId: string;
  targetId: string;
  indices: GraphIndices;
}) {
  const { sourceId, targetId, indices } = args;
  const leftType = resolveRecordType(sourceId, indices.stepsById);
  const rightType = resolveRecordType(targetId, indices.stepsById);
  const recordType =
    leftType != null && leftType !== "" && leftType !== "__mismatch__"
      ? leftType
      : rightType;
  const mismatch =
    Boolean(leftType) &&
    Boolean(rightType) &&
    leftType !== rightType &&
    leftType !== "__mismatch__" &&
    rightType !== "__mismatch__";
  return { recordType: recordType ?? null, mismatch };
}
