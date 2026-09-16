import type { Step, StepKind } from "@pathfinder/shared";

const OPERATOR_NAME: Record<string, string> = {
  INTERSECT: "Intersect",
  UNION: "Union",
  MINUS: "Minus",
  RMINUS: "Minus (reversed)",
  LONLY: "Left only",
  RONLY: "Right only",
  COLOCATE: "Colocated",
};

export function operatorName(operator: string): string {
  return OPERATOR_NAME[operator] ?? operator;
}

/**
 * The name a step shows on the canvas, or "" when it has none. A combine whose
 * display name is the search name behind it carries WDK's question name, which
 * is not a name; it is named by the operation it performs.
 */
export function stepTitle(step: Step, kind: StepKind): string {
  const given = step.displayName ?? "";
  if (kind !== "combine" || (given !== "" && given !== step.searchName)) {
    return given;
  }
  const operator = step.operator ?? "";
  return operator === "" ? "Combine" : operatorName(operator);
}
