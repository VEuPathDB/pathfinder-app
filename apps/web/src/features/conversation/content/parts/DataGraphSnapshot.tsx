import type { GraphSnapshot } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

import { geneCountClause } from "./geneCount";

export function DataGraphSnapshot({ data }: { data: GraphSnapshot }) {
  const stepCount = data.nodes.length;
  const stepLabel = stepCount === 1 ? "step" : "steps";
  return (
    <Figure
      testId="data-graph-snapshot"
      title="Strategy updated"
      caption={`${stepCount.toLocaleString()} ${stepLabel}, ${geneCountClause(data.geneCount)}`}
    >
      {null}
    </Figure>
  );
}
