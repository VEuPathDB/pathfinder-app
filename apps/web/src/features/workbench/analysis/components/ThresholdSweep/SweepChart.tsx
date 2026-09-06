import { Loader2 } from "lucide-react";

import type { ThresholdSweepPoint } from "@/features/workbench/analysis/api/compute";
import { EChart } from "@/lib/components/charts/EChart";
import { readChartTokens } from "@/lib/components/charts/chartTheme";
import { buildSweepChartOption } from "./sweepChart.options";

export function SweepChart({
  points,
  parameter,
  sweepType,
  formatValue,
  isStreaming,
}: {
  points: ThresholdSweepPoint[];
  parameter: string;
  sweepType: "numeric" | "categorical";
  formatValue: (v: number | string) => string;
  isStreaming: boolean;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        Metrics vs {parameter}
        {isStreaming && (
          <span className="flex items-center gap-1 text-primary">
            <Loader2 className="h-3 w-3 animate-spin" />
            streaming
          </span>
        )}
      </div>
      <EChart
        option={buildSweepChartOption({
          points,
          parameter,
          sweepType,
          formatValue,
          tokens: readChartTokens(),
        })}
        height={260}
        ariaLabel={`Sensitivity, specificity and F1 over ${parameter}`}
        testId="sweep-chart"
      />
    </div>
  );
}
