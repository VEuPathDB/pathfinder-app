import type { StepKind } from "@pathfinder/shared";

type StepLike = {
  kind?: StepKind | string | null;
  searchName?: string | null;
  primaryInputStepId?: string | null;
  secondaryInputStepId?: string | null;
  operator?: string | null;
};

export function inferStepKind(step: StepLike): StepKind {
  if (step.kind === "search" || step.kind === "transform" || step.kind === "combine")
    return step.kind;
  if (step.primaryInputStepId != null && step.secondaryInputStepId != null)
    return "combine";
  // A step with an operator or the __combine__ sentinel is a combine step even
  // if its inputs were lost (e.g. broken persisted plan). Recognising it as
  // "combine" prevents validation from sending __combine__ to WDK as a search.
  if (step.operator != null && step.operator !== "") return "combine";
  if (step.searchName === "__combine__") return "combine";
  if (step.primaryInputStepId != null) return "transform";
  return "search";
}
