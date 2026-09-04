import type { Step } from "@pathfinder/shared";

type StrategyGraphErrorSeverity = "error" | "info";

export type StrategyGraphError = {
  code:
    | "MISSING_INPUT"
    | "UNKNOWN_STEP"
    | "MISSING_OPERATOR"
    | "MISSING_SEARCH_NAME"
    | "ORPHAN_STEP"
    | "MULTIPLE_ROOTS";
  severity: StrategyGraphErrorSeverity;
  message: string;
  stepId?: string;
  inputStepId?: string;
};

type CombineRecordTypeMismatch = {
  stepId: string;
  leftType: string | null;
  rightType: string | null;
};

export type CombineMismatchGroup = {
  id: string;
  ids: Set<string>;
  message: string;
};

function inferKind(step: Step): "search" | "transform" | "combine" | "invalid" {
  if (step.secondaryInputStepId != null && step.primaryInputStepId == null)
    return "invalid";
  if (step.primaryInputStepId != null && step.secondaryInputStepId != null)
    return "combine";
  // A step with an operator (or explicit kind="combine") is a combine even if
  // one or both inputs were removed.  This ensures combine-specific checks
  // (two inputs required, operator required, etc.) still fire.
  if ((step.operator != null && step.operator !== "") || step.kind === "combine")
    return "combine";
  if (step.primaryInputStepId != null) return "transform";
  return "search";
}

export function resolveRecordType(
  stepId: string | null | undefined,
  stepsMap: Map<string, Step>,
): string | null {
  if (stepId == null) return null;
  const step = stepsMap.get(stepId);
  if (step == null) return null;
  if (step.recordType != null && step.recordType !== "") return step.recordType;
  const kind = inferKind(step);
  if (kind === "transform" && step.primaryInputStepId != null) {
    return resolveRecordType(step.primaryInputStepId, stepsMap);
  }
  if (kind === "combine") {
    const left = resolveRecordType(step.primaryInputStepId, stepsMap);
    const right = resolveRecordType(step.secondaryInputStepId, stepsMap);
    if (left != null && right != null && left !== right) return "__mismatch__";
    return left ?? right ?? null;
  }
  return null;
}

export function findCombineRecordTypeMismatch(
  stepsList: Step[],
): CombineRecordTypeMismatch | null {
  const stepsMap = new Map(stepsList.map((step) => [step.id, step]));
  for (const step of stepsList) {
    if (inferKind(step) !== "combine") continue;
    const leftType = resolveRecordType(step.primaryInputStepId, stepsMap);
    const rightType = resolveRecordType(step.secondaryInputStepId, stepsMap);
    if (
      leftType != null &&
      rightType != null &&
      leftType !== rightType &&
      leftType !== "__mismatch__" &&
      rightType !== "__mismatch__"
    ) {
      return { stepId: step.id, leftType, rightType };
    }
    if (leftType === "__mismatch__" || rightType === "__mismatch__") {
      return { stepId: step.id, leftType, rightType };
    }
  }
  return null;
}

export function getRootSteps(steps: Step[]): Step[] {
  if (steps.length === 0) return [];
  const referenced = new Set<string>();
  for (const step of steps) {
    if (step.primaryInputStepId != null) referenced.add(step.primaryInputStepId);
    if (step.secondaryInputStepId != null) referenced.add(step.secondaryInputStepId);
  }
  return steps.filter((step) => !referenced.has(step.id));
}

export function getCombineMismatchGroups(steps: Step[]): CombineMismatchGroup[] {
  if (steps.length === 0) return [];
  const stepsMap = new Map(steps.map((step) => [step.id, step]));
  const groups: CombineMismatchGroup[] = [];
  for (const step of steps) {
    if (inferKind(step) !== "combine") continue;
    const leftType = resolveRecordType(step.primaryInputStepId, stepsMap);
    const rightType = resolveRecordType(step.secondaryInputStepId, stepsMap);
    if (leftType == null || rightType == null) continue;
    if (
      leftType === "__mismatch__" ||
      rightType === "__mismatch__" ||
      leftType !== rightType
    ) {
      const ids = new Set<string>([step.id]);
      if (step.primaryInputStepId != null) ids.add(step.primaryInputStepId);
      if (step.secondaryInputStepId != null) ids.add(step.secondaryInputStepId);
      groups.push({
        id: step.id,
        ids,
        message: "Cannot combine steps with different record types.",
      });
    }
  }
  return groups;
}

export function validateStrategySteps(steps: Step[]): StrategyGraphError[] {
  const errors: StrategyGraphError[] = [];
  if (steps.length === 0) return errors;

  const stepIds = new Set(steps.map((step) => step.id));
  const referenced = new Set<string>();

  for (const step of steps) {
    const kind = inferKind(step);
    // Combine steps use a canonical searchName ("boolean_question") during serialization;
    // the UI doesn't store this on the step, so don't block on it here.
    if ((step.searchName == null || step.searchName === "") && kind !== "combine") {
      errors.push({
        code: "MISSING_SEARCH_NAME",
        severity: "error",
        message: "searchName is required.",
        stepId: step.id,
      });
    }

    if (kind === "invalid") {
      errors.push({
        code: "MISSING_INPUT",
        severity: "error",
        message: "secondaryInput requires primaryInput.",
        stepId: step.id,
      });
    }

    if (kind === "combine") {
      if (step.operator == null || step.operator === "") {
        errors.push({
          code: "MISSING_OPERATOR",
          severity: "error",
          message: "Combine steps require an operator.",
          stepId: step.id,
        });
      }
      if (step.operator === "COLOCATE" && step.colocationParams == null) {
        errors.push({
          code: "MISSING_INPUT",
          severity: "error",
          message: "COLOCATE requires colocationParams.",
          stepId: step.id,
        });
      }
      if (step.primaryInputStepId == null || step.secondaryInputStepId == null) {
        errors.push({
          code: "MISSING_INPUT",
          severity: "error",
          message: "Combine steps require two inputs.",
          stepId: step.id,
        });
      }
    }

    if (step.primaryInputStepId != null) referenced.add(step.primaryInputStepId);
    if (step.secondaryInputStepId != null) referenced.add(step.secondaryInputStepId);

    if (step.primaryInputStepId != null && !stepIds.has(step.primaryInputStepId)) {
      errors.push({
        code: "UNKNOWN_STEP",
        severity: "error",
        message: "Primary input step does not exist.",
        stepId: step.id,
        inputStepId: step.primaryInputStepId,
      });
    }
    if (step.secondaryInputStepId != null && !stepIds.has(step.secondaryInputStepId)) {
      errors.push({
        code: "UNKNOWN_STEP",
        severity: "error",
        message: "Secondary input step does not exist.",
        stepId: step.id,
        inputStepId: step.secondaryInputStepId,
      });
    }
  }

  const roots = getRootSteps(steps);
  if (roots.length === 0) {
    errors.push({
      code: "ORPHAN_STEP",
      severity: "info",
      message: "Strategy graph has no root steps.",
    });
  } else if (roots.length > 1) {
    errors.push({
      code: "MULTIPLE_ROOTS",
      severity: "info",
      message:
        "Strategy graph has more than one root; only the rooted component is pushed.",
    });
  }

  return errors;
}
