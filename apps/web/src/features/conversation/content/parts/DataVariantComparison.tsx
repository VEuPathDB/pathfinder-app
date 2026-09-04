import type { VariantComparison } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

const TRUNCATED_NOTE = "large result sets, overlap is a lower bound";

function largestGeneCount(data: VariantComparison): number {
  return data.variants.reduce((best, variant) => Math.max(best, variant.geneCount), 0);
}

export function DataVariantComparison({ data }: { data: VariantComparison }) {
  return (
    <Figure
      testId="data-variant-comparison"
      title="Variants"
      caption={`${data.variants.length.toLocaleString()} variants, ${largestGeneCount(data).toLocaleString()} genes in the largest`}
    >
      <div className="text-xs">
        {data.truncated === true ? (
          <p className="text-[10px] text-muted-foreground">{TRUNCATED_NOTE}</p>
        ) : null}

        <ul className="space-y-1.5">
          {data.variants.map((v) => (
            <li key={v.label}>
              <div className="flex items-baseline gap-2">
                <span className="font-medium text-foreground">{v.label}</span>
                <span className="ml-auto font-mono text-[11px] text-foreground">
                  {v.error != null && v.error !== ""
                    ? "-"
                    : `${v.geneCount.toLocaleString()} genes`}
                </span>
              </div>
              {v.error != null && v.error !== "" ? (
                <div className="mt-0.5 text-[11px] text-destructive">
                  failed: {v.error}
                </div>
              ) : (
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {v.uniqueCount.toLocaleString()} unique
                  {v.sampleUniqueGenes.length > 0 ? (
                    <span className="font-mono">
                      {` - ${v.sampleUniqueGenes.join(", ")}`}
                    </span>
                  ) : null}
                </div>
              )}
            </li>
          ))}
        </ul>

        {data.overlaps.length > 0 ? (
          <dl className="mt-2 space-y-0.5 pt-1.5">
            {data.overlaps.map((o) => (
              <div key={`${o.a}|${o.b}`} className="flex gap-2 text-[11px]">
                <dt className="text-muted-foreground">
                  {o.a} vs {o.b}
                </dt>
                <dd className="ml-auto font-mono text-foreground">
                  {`${o.shared.toLocaleString()} shared, Jaccard ${String(o.jaccard)}`}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </Figure>
  );
}
