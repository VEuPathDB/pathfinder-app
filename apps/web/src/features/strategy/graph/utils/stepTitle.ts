import type { Step, StepKind } from "@pathfinder/shared";
import { isOperatorLabel, operatorLabel } from "@/features/strategy/operators";

/**
 * The name a step shows on the canvas, or "" when it has none. A combine is
 * named by its operation unless a researcher named it: an operator's label
 * and the search name WDK gives an unnamed step are not names.
 */
export function stepTitle(step: Step, kind: StepKind): string {
  const given = step.displayName ?? "";
  if (kind !== "combine") return given;
  if (given !== "" && given !== step.searchName && !isOperatorLabel(given)) {
    return given;
  }
  const operator = step.operator ?? "";
  return operator === "" ? "Combine" : operatorLabel(operator);
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

/** The reason in full, and the names of the searches it was chosen over. */
export function reasonDetail(rationale: StepRationale): string {
  if (rationale.kind === "analysis") return rationale.reason;
  if (rationale.kind === "controls") {
    return (
      `chosen by the controls: ${rationale.short}, ` +
      `${rationale.resultSize.toLocaleString("en-US")} genes (${rationale.basis})`
    );
  }
  const considered = (rationale.compared ?? []).map((search) => search.displayName);
  return considered.length === 0
    ? rationale.sentence
    : `${rationale.sentence}\nAlso considered: ${considered.join(", ")}`;
}
