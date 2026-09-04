import type { Strategy } from "@pathfinder/shared";
import {
  applyAddCombine,
  applyAddLeaf,
  applyAddTransform,
  applyDuplicateStep,
} from "./applyAdd";
import { applyDeleteStep } from "./applyDelete";
import {
  applyDeleteEdge,
  applyReplaceStrategy,
  applyUpdateCombineOperator,
  applyUpdateStepMeta,
  applyUpdateStepParams,
  applyUpdateStrategyMeta,
  applyWireInput,
} from "./applyUpdate";
import type { GraphOperation } from "@/lib/types/graphOperation";
import type { ApplyResult } from "./types";

export function applyOperation(strategy: Strategy, op: GraphOperation): ApplyResult {
  switch (op.kind) {
    case "addLeaf":
      return applyAddLeaf(strategy, op);
    case "addCombine":
      return applyAddCombine(strategy, op);
    case "addTransform":
      return applyAddTransform(strategy, op);
    case "duplicateStep":
      return applyDuplicateStep(strategy, op);
    case "deleteStep":
      return applyDeleteStep(strategy, op);
    case "deleteEdge":
      return applyDeleteEdge(strategy, op, applyOperation);
    case "updateStepParams":
      return applyUpdateStepParams(strategy, op);
    case "updateCombineOperator":
      return applyUpdateCombineOperator(strategy, op);
    case "updateStepMeta":
      return applyUpdateStepMeta(strategy, op);
    case "updateStrategyMeta":
      return applyUpdateStrategyMeta(strategy, op);
    case "wireInput":
      return applyWireInput(strategy, op);
    case "replaceStrategy":
      return applyReplaceStrategy(strategy, op);
  }
}
