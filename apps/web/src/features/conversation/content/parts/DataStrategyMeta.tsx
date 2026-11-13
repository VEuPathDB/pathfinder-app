import type { StrategyMeta } from "@strategist/shared";

import { Figure } from "@/features/conversation/thread/Figure";

import { geneCountClause } from "./geneCount";

export function DataStrategyMeta({ data }: { data: StrategyMeta }) {
  const saved = data.isSaved ? ", saved" : "";
  return (
    <Figure
      testId="data-strategy-meta"
      title={null}
      caption={`${data.name} - ${geneCountClause(data.estimatedSize)}${saved}`}
    >
      {null}
    </Figure>
  );
}
