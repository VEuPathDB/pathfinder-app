import type { EnrichmentTerm } from "@pathfinder/shared";

import { EChart } from "@/lib/components/charts/EChart";
import { readChartTokens } from "@/lib/components/charts/chartTheme";
import { buildEnrichmentDotPlot } from "./enrichmentDotPlot.options";
import { DOT_MAX_R, DOT_MIN_R, pvalColor, pvalGradient } from "./enrichment-utils";

function DotPlotLegend({ maxGeneCount }: { maxGeneCount: number }) {
  const sizes = [
    { count: Math.max(1, Math.round(maxGeneCount * 0.1)), r: DOT_MIN_R },
    {
      count: Math.max(2, Math.round(maxGeneCount * 0.5)),
      r: (DOT_MIN_R + DOT_MAX_R) / 2,
    },
    { count: maxGeneCount, r: DOT_MAX_R },
  ];
  return (
    <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
      <span className="flex items-center gap-1">
        <span
          className="inline-block h-2 w-8 rounded-sm"
          style={{ background: pvalGradient() }}
        />
        <span>-log10(p)</span>
      </span>
      <span className="flex items-center gap-1.5">
        {sizes.map((s) => (
          <span key={s.count} className="flex items-center gap-0.5">
            <svg width={s.r * 2 + 2} height={s.r * 2 + 2}>
              <circle
                cx={s.r + 1}
                cy={s.r + 1}
                r={s.r}
                fill="hsl(var(--muted-foreground))"
                fillOpacity={0.3}
                stroke="hsl(var(--muted-foreground))"
                strokeWidth={0.5}
              />
            </svg>
            <span>{s.count}</span>
          </span>
        ))}
        <span>genes</span>
      </span>
    </div>
  );
}

interface EnrichmentDotPlotProps {
  terms: EnrichmentTerm[];
}

export function EnrichmentDotPlot({ terms }: EnrichmentDotPlotProps) {
  const model = buildEnrichmentDotPlot({
    terms,
    tokens: readChartTokens(),
    colorForPValue: pvalColor,
  });

  return (
    <div className="border-b border-border/50 px-4 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Top {model.termCount} Terms by Significance
        </h4>
        <DotPlotLegend maxGeneCount={model.maxGeneCount} />
      </div>
      <EChart
        option={model.option}
        height={model.height}
        ariaLabel={`Fold enrichment of the top ${String(model.termCount)} terms by significance`}
        testId="enrichment-dot-plot"
      />
    </div>
  );
}
