import type { GraphSnapshot } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

import { geneCountClause } from "./geneCount";

/** The steps the strategy's tree leaves out, named rather than counted in. */
function detachedClause(count: number | undefined): string {
  if (count === undefined || count === 0) return "";
  const label = count === 1 ? "step" : "steps";
  return `, ${count.toLocaleString()} ${label} not in the strategy`;
}

export function DataGraphSnapshot({ data }: { data: GraphSnapshot }) {
  const stepCount = data.nodes.length;
  const stepLabel = stepCount === 1 ? "step" : "steps";
  const genes = geneCountClause(data.geneCount);
  const detached = detachedClause(data.detachedStepCount);
  return (
    <Figure
      testId="data-graph-snapshot"
      title="Strategy updated"
      caption={`${stepCount.toLocaleString()} ${stepLabel}, ${genes}${detached}`}
    >
      {null}
    </Figure>
  );
}
