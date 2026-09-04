"use client";

import type { Step } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";
import type { GraphOperation } from "@/features/strategy/operations";
import { useApplyOperation } from "./useApplyOperation";

export interface AddStepVars {
  step: Step;
}

function stepToOp(step: Step): GraphOperation {
  const kind = inferStepKind(step);
  if (kind === "combine") {
    if (step.primaryInputStepId == null || step.secondaryInputStepId == null) {
      throw new Error("Combine step missing primary or secondary input");
    }
    return {
      kind: "addCombine",
      step,
      leftId: step.primaryInputStepId,
      rightId: step.secondaryInputStepId,
    };
  }
  if (kind === "transform") {
    if (step.primaryInputStepId == null) {
      throw new Error("Transform step missing primary input");
    }
    return {
      kind: "addTransform",
      step,
      inputId: step.primaryInputStepId,
      mode: "new-root",
    };
  }
  return { kind: "addLeaf", step, attach: { mode: "new-root" } };
}

export function useAddStepMutation(conversationId: string) {
  const apply = useApplyOperation(conversationId);
  return {
    ...apply,
    mutate: (vars: AddStepVars) => {
      apply.mutate({ op: stepToOp(vars.step) });
    },
    mutateAsync: async (vars: AddStepVars) => {
      return apply.mutateAsync({ op: stepToOp(vars.step) });
    },
  };
}
