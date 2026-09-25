import type { Step } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";
import { combineOpEnum } from "@pathfinder/shared";
import { operatorLabel } from "@/features/strategy/operators";

export function getZeroResultSuggestions(step: Step): string[] {
  const suggestions: string[] = [];

  // Broad, always-relevant suggestions
  suggestions.push(
    "Relax overly strict parameters/filters (broader thresholds, stages, experiments).",
  );
  suggestions.push(
    "Check that the organism / life stage / strain matches the experiment or search you picked.",
  );

  const kind = inferStepKind(step);
  if (kind === "combine") {
    const op = step.operator;
    if (op === combineOpEnum.INTERSECT) {
      suggestions.push(
        `If you expected results from either input, change ${operatorLabel(combineOpEnum.INTERSECT)} to ${operatorLabel(combineOpEnum.UNION)}.`,
      );
    } else if (
      op === combineOpEnum.MINUS ||
      op === combineOpEnum.LONLY ||
      op === combineOpEnum.RMINUS ||
      op === combineOpEnum.RONLY
    ) {
      suggestions.push(
        `If you expected the other input removed, check the direction: swap ${operatorLabel(combineOpEnum.MINUS)} and ${operatorLabel(combineOpEnum.RMINUS)}.`,
      );
    } else if (op === combineOpEnum.COLOCATE) {
      suggestions.push(
        `For ${operatorLabel(combineOpEnum.COLOCATE)}, widen the region offsets and check the feature types.`,
      );
    }
    suggestions.push("Check that both input steps are non-zero before combining.");
  } else if (kind === "transform") {
    suggestions.push(
      "If the input step is zero, fix upstream; otherwise adjust transform parameters.",
    );
    suggestions.push(
      "For cross-species mapping, consider an orthology transform (find orthologs) before/after this step.",
    );
  } else {
    suggestions.push(
      "Try an alternative search with similar meaning (broader keyword / different experiment).",
    );
  }

  // Keep it short; UI should not overwhelm.
  return suggestions.slice(0, 5);
}
