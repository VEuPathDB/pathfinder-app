import type { StrategyMeta } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

export function DataStrategyMeta({ data }: { data: StrategyMeta }) {
  const saved = data.isSaved ? ", saved" : "";
  return (
    <Figure
      testId="data-strategy-meta"
      title={null}
      caption={`${data.name} - ${data.estimatedSize.toLocaleString()} genes${saved}`}
    >
      {null}
    </Figure>
  );
}
