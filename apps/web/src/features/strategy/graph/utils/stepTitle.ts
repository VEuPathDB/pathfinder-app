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

const OPERATOR_NAMES = new Set(Object.values(OPERATOR_NAME));

export function operatorName(operator: string): string {
  return OPERATOR_NAME[operator] ?? operator;
}

/**
 * The name a step shows on the canvas, or "" when it has none. A combine is
 * named by its operation unless a researcher named it: an operator's label
 * and the search name WDK gives an unnamed step are not names.
 */
export function stepTitle(step: Step, kind: StepKind): string {
  const given = step.displayName ?? "";
  if (kind !== "combine") return given;
  if (given !== "" && given !== step.searchName && !OPERATOR_NAMES.has(given)) {
    return given;
  }
  const operator = step.operator ?? "";
  return operator === "" ? "Combine" : operatorName(operator);
}

/**
 * The request's words a search or transform stands for, or "" when the step
 * carries none or they repeat its title. The title names the search that runs.
 */
export function stepSubtitle(step: Step, kind: StepKind): string {
  if (kind === "combine") return "";
  const words = step.criterionText ?? "";
  return words === stepTitle(step, kind) ? "" : words;
}

type StepRationale = NonNullable<Step["rationale"]>;

/**
 * Why a search or transform runs what it runs, as the api labels it, or ""
 * when the step records no reason.
 */
export function stepReason(step: Step, kind: StepKind): string {
  if (kind === "combine") return "";
  return step.rationale?.short ?? "";
}

/** The reason in full, and the searches it was chosen over with their scores. */
export function reasonDetail(rationale: StepRationale): string {
  if (rationale.kind === "analysis") return rationale.reason;
  const over = (rationale.compared ?? []).map((search) =>
    search.similarity == null
      ? search.displayName
      : `${search.displayName} ${search.similarity.toFixed(2)}`,
  );
  return over.length === 0
    ? rationale.reason
    : `${rationale.reason} (over ${over.join(", ")})`;
}
