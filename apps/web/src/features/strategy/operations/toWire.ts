import type { Step, StrategyStepNode } from "@pathfinder/shared";
import type { ApplyOperationRequest } from "@pathfinder/shared/generated/types/ApplyOperationRequest";
import type { GraphOperation } from "@/lib/types/graphOperation";

export type WireOperation = ApplyOperationRequest["op"];

/**
 * Project a canvas step onto the node shape the API models.
 *
 * The reducer carries display state (`status`, `recordType`, counts) and
 * addresses inputs by id so it can splice a flat `Strategy.steps`. The API
 * models a node. Sending the canvas shape wholesale is not an error the API
 * reports - Pydantic's `extra="ignore"` drops the unknown keys silently - so
 * the projection is written out rather than left to chance.
 *
 * Inputs are deliberately absent: every operation that adds a step carries its
 * wiring in sibling fields (`attach`, `leftId`/`rightId`, `inputId`).
 */
function toNode(step: Step): StrategyStepNode {
  return {
    id: step.id,
    searchName: step.searchName ?? "",
    displayName: step.displayName ?? "",
    parameters: step.parameters ?? {},
  };
}

/**
 * Convert a reducer operation into the request body the API accepts.
 *
 * The declared return type is the generated union, so an operation the backend
 * does not implement fails `tsc` rather than the request. This replaced an
 * `as` cast that had let a frontend-only `deleteEdge` reach production, where
 * it 422'd on every use.
 */
export function toWireOperation(op: GraphOperation): WireOperation {
  switch (op.kind) {
    case "addLeaf":
      return { kind: "addLeaf", step: toNode(op.step), attach: op.attach };
    case "addCombine":
      return {
        kind: "addCombine",
        step: toNode(op.step),
        leftId: op.leftId,
        rightId: op.rightId,
      };
    case "addTransform":
      return {
        kind: "addTransform",
        step: toNode(op.step),
        inputId: op.inputId,
        mode: op.mode,
      };
    case "duplicateStep":
      return {
        kind: "duplicateStep",
        sourceStepId: op.sourceStepId,
        duplicateStepId: op.duplicateStepId,
        combineStepId: op.combineStepId,
        combineDisplayName: op.combineDisplayName ?? null,
      };
    case "deleteStep":
      return { kind: "deleteStep", stepId: op.stepId, resolution: op.resolution };
    case "deleteEdge":
      return {
        kind: "deleteEdge",
        sourceId: op.sourceId,
        targetId: op.targetId,
        slot: op.slot,
        resolution: op.resolution,
      };
    case "updateStepParams":
      return {
        kind: "updateStepParams",
        stepId: op.stepId,
        parameters: op.parameters,
      };
    case "updateCombineOperator":
      return {
        kind: "updateCombineOperator",
        stepId: op.stepId,
        operator: op.operator,
        colocationParams: op.colocationParams ?? null,
      };
    case "updateStepMeta":
      return {
        kind: "updateStepMeta",
        stepId: op.stepId,
        displayName: op.displayName,
      };
    case "updateStrategyMeta":
      return {
        kind: "updateStrategyMeta",
        name: op.name ?? null,
        description: op.description ?? null,
      };
    case "wireInput":
      return {
        kind: "wireInput",
        targetStepId: op.targetStepId,
        slot: op.slot,
        sourceStepId: op.sourceStepId,
      };
    case "replaceStrategy":
      return {
        kind: "replaceStrategy",
        root: op.root,
        name: op.name ?? null,
        description: op.description ?? null,
      };
  }
}
