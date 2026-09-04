import type { GraphSnapshot } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

export function DataGraphSnapshot({ data }: { data: GraphSnapshot }) {
  const stepCount = data.nodes.length;
  const stepLabel = stepCount === 1 ? "step" : "steps";
  return (
    <Figure
      testId="data-graph-snapshot"
      title="Strategy updated"
      caption={`${stepCount.toLocaleString()} ${stepLabel}, ${data.geneCount.toLocaleString()} genes`}
    >
      {null}
    </Figure>
  );
}
