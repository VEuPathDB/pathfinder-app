import type { Step } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";
import { combineOpEnum } from "@pathfinder/shared";

export function getZeroResultSuggestions(step: Step): string[] {
  const suggestions: string[] = [];

  // Broad, always-relevant suggestions
  suggestions.push(
    "Relax overly strict parameters/filters (broader thresholds, stages, datasets).",
  );
  suggestions.push(
    "Verify organism / life stage / strain matches the dataset/search you picked.",
  );

  const kind = inferStepKind(step);
  if (kind === "combine") {
    const op = step.operator;
    if (op === combineOpEnum.INTERSECT) {
      suggestions.push(
        "If you expected results from either branch, change INTERSECT (AND) to UNION (OR).",
      );
    } else if (
      op === combineOpEnum.MINUS ||
      op === combineOpEnum.LONLY ||
      op === combineOpEnum.RMINUS ||
      op === combineOpEnum.RONLY
    ) {
      suggestions.push(
        "If you expected to remove the other branch, verify MINUS direction (swap MINUS vs RMINUS).",
      );
    } else if (op === combineOpEnum.COLOCATE) {
      suggestions.push(
        "For COLOCATE/NEAR, widen the region offsets and verify feature types.",
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
      "Try an alternative search with similar meaning (broader keyword / different dataset).",
    );
  }

  // Keep it short; UI should not overwhelm.
  return suggestions.slice(0, 5);
}
