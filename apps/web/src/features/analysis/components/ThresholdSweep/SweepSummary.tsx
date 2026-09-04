import { TrendingUp, Target, AlertTriangle } from "lucide-react";
import type { ThresholdSweepPoint } from "@/features/analysis/api/compute";
import { Card } from "@/components/ui/card";
import { pct } from "../../utils/formatters";

export function SweepSummary({
  points,
  parameter,
  sweepType,
  formatValue,
  currentValue,
  failedCount,
}: {
  points: ThresholdSweepPoint[];
  parameter: string;
  sweepType: "numeric" | "categorical";
  formatValue: (v: number | string) => string;
  currentValue?: string;
  failedCount: number;
}) {
  const bestF1 = points.reduce((best, p) =>
    (p.metrics?.f1Score ?? 0) > (best.metrics?.f1Score ?? 0) ? p : best,
  );
  const bestBalAcc = points.reduce((best, p) =>
    (p.metrics?.balancedAccuracy ?? 0) > (best.metrics?.balancedAccuracy ?? 0)
      ? p
      : best,
  );
  const bestSens = points.reduce((best, p) =>
    (p.metrics?.sensitivity ?? 0) > (best.metrics?.sensitivity ?? 0) ? p : best,
  );

  const currentPoint =
    currentValue != null
      ? sweepType === "numeric"
        ? points.reduce((closest, p) =>
            Math.abs(Number(p.value) - Number(currentValue)) <
            Math.abs(Number(closest.value) - Number(currentValue))
              ? p
              : closest,
          )
        : (points.find((p) => String(p.value) === currentValue) ?? null)
      : null;

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-4 space-y-3">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <TrendingUp className="h-3.5 w-3.5" />
        Sweep Summary
      </h4>

      <div className="grid grid-cols-3 gap-4">
        <SummaryCard
          label="Best F1 Score"
          value={pct(bestF1.metrics?.f1Score)}
          detail={`at ${parameter} = ${formatValue(bestF1.value)}`}
        />
        <SummaryCard
          label="Best Balanced Accuracy"
          value={pct(bestBalAcc.metrics?.balancedAccuracy)}
          detail={`at ${parameter} = ${formatValue(bestBalAcc.value)}`}
        />
        <SummaryCard
          label="Best Sensitivity"
          value={pct(bestSens.metrics?.sensitivity)}
          detail={`at ${parameter} = ${formatValue(bestSens.value)}`}
        />
      </div>

      {currentPoint && currentValue != null && (
        <Card className="flex items-start gap-2 rounded-md px-3 py-2">
          <Target className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <div className="text-xs">
            <span className="text-muted-foreground">Current value </span>
            <span className="font-mono font-medium text-foreground">
              {parameter} = {formatValue(currentValue)}
            </span>
            <span className="text-muted-foreground"> yields </span>
            <span className="font-medium text-foreground">
              F1 {pct(currentPoint.metrics?.f1Score)}
            </span>
            {bestF1.value !== currentPoint.value && (
              <>
                <span className="text-muted-foreground">. Consider </span>
                <span className="font-mono font-medium text-primary">
                  {formatValue(bestF1.value)}
                </span>
                <span className="text-muted-foreground"> for peak F1 </span>
                <span className="font-medium text-primary">
                  {pct(bestF1.metrics?.f1Score)}
                </span>
              </>
            )}
          </div>
        </Card>
      )}

      {failedCount > 0 && (
        <div className="flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle className="h-3 w-3" />
          {failedCount} point{failedCount !== 1 ? "s" : ""} failed (timeout or site
          error)
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <Card className="rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-lg font-semibold tabular-nums text-foreground">{value}</div>
      <div className="text-[10px] text-muted-foreground">{detail}</div>
    </Card>
  );
}
