import type { GeneSetPart } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

export function DataGeneSet({ data }: { data: GeneSetPart }) {
  return (
    <Figure
      testId="data-gene-set"
      title={data.name}
      caption={`${data.geneCount.toLocaleString()} genes on ${data.siteId}`}
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="inline-block size-1.5 rounded-full bg-success" />
        <span>Gene set created</span>
      </div>
    </Figure>
  );
}
