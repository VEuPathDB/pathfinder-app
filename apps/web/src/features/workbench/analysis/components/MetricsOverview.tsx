import { useState } from "react";
import type { ExperimentMetrics } from "@pathfinder/shared";
import { EChart } from "@/lib/components/charts/EChart";
import { readChartTokens } from "@/lib/components/charts/chartTheme";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { Section } from "./Section";
import { buildMetricsRadarOption } from "./metricsRadar.options";
import { pct, fmtNum } from "../utils/formatters";

interface MetricsOverviewProps {
  metrics: ExperimentMetrics;
}

function metricValueColor(value: number, raw?: boolean | null): string {
  const normalized = raw === true ? (value + 1) / 2 : value; // MCC is [-1,1]
  if (normalized >= 0.7) return "text-success";
  if (normalized >= 0.4) return "text-warning";
  return "text-destructive";
}

export function MetricsOverview({ metrics }: MetricsOverviewProps) {
  const [showSecondary, setShowSecondary] = useState(false);

  interface MetricRow {
    label: string;
    value: number;
    desc: string;
    raw?: boolean;
  }

  const primary: MetricRow[] = [
    {
      label: "Sensitivity",
      value: metrics.sensitivity,
      desc: "TP / (TP + FN) \u2014 proportion of true positives correctly identified",
    },
    {
      label: "Specificity",
      value: metrics.specificity,
      desc: "TN / (TN + FP) \u2014 proportion of true negatives correctly identified",
    },
    {
      label: "Precision",
      value: metrics.precision,
      desc: "TP / (TP + FP) \u2014 proportion of predicted positives that are correct",
    },
    {
      label: "F1 Score",
      value: metrics.f1Score,
      desc: "2 \u00d7 (Precision \u00d7 Sensitivity) / (Precision + Sensitivity) \u2014 harmonic mean",
    },
    {
      label: "MCC",
      value: metrics.mcc,
      desc: "Matthews Correlation Coefficient \u2014 balanced measure even with class imbalance, range [-1, 1]",
      raw: true,
    },
    {
      label: "Balanced Accuracy",
      value: metrics.balancedAccuracy,
      desc: "(Sensitivity + Specificity) / 2 \u2014 accounts for class imbalance",
    },
  ];

  const secondary: MetricRow[] = [
    {
      label: "NPV",
      value: metrics.negativePredictiveValue ?? 0,
      desc: "TN / (TN + FN) \u2014 negative predictive value",
    },
    {
      label: "FPR",
      value: metrics.falsePositiveRate ?? 0,
      desc: "FP / (FP + TN) \u2014 false positive rate",
    },
    {
      label: "FNR",
      value: metrics.falseNegativeRate ?? 0,
      desc: "FN / (FN + TP) \u2014 false negative rate",
    },
    {
      label: "Youden\u2019s J",
      value: metrics.youdensJ ?? 0,
      raw: true,
      desc: "Sensitivity + Specificity - 1 \u2014 ranges from -1 to 1",
    },
  ];

  return (
    <div data-testid="metrics-overview" className="space-y-6">
      {/* Classification metrics */}
      <Section title="Classification Metrics">
        <Card>
          <div className="grid grid-cols-[1fr_280px] divide-x divide-border max-lg:grid-cols-1 max-lg:divide-x-0 max-lg:divide-y">
            <div>
              {primary.map((m) => (
                <div
                  key={m.label}
                  data-testid="metric-row"
                  data-metric={m.label}
                  className="flex items-center justify-between border-b border-border px-5 py-2.5 last:border-b-0"
                >
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="cursor-help">
                        <span className="text-sm font-medium text-foreground">
                          {m.label}
                        </span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs">
                      <p>{m.desc}</p>
                    </TooltipContent>
                  </Tooltip>
                  <span
                    className={`font-mono text-sm font-semibold tabular-nums ${metricValueColor(m.value, m.raw)}`}
                  >
                    {m.raw === true ? fmtNum(m.value) : pct(m.value)}
                  </span>
                </div>
              ))}

              {showSecondary && (
                <>
                  <Separator />
                  {secondary.map((m) => (
                    <div
                      key={m.label}
                      className="flex items-center justify-between bg-muted/30 px-5 py-2.5"
                    >
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="cursor-help text-sm text-muted-foreground">
                            {m.label}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-xs">
                          <p>{m.desc}</p>
                        </TooltipContent>
                      </Tooltip>
                      <span
                        className={`font-mono text-sm tabular-nums ${metricValueColor(m.value, m.raw)}`}
                      >
                        {m.raw === true ? fmtNum(m.value) : pct(m.value)}
                      </span>
                    </div>
                  ))}
                </>
              )}

              <div className="px-5 py-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setShowSecondary(!showSecondary)}
                >
                  {showSecondary ? "Show less" : "Show all metrics"}
                </Button>
              </div>
            </div>

            <div className="flex items-center justify-center p-4 max-lg:py-6">
              <EChart
                option={buildMetricsRadarOption({
                  metrics,
                  tokens: readChartTokens(),
                })}
                height={220}
                ariaLabel="Radar of the six classification metrics"
                testId="metrics-radar"
              />
            </div>
          </div>
        </Card>
      </Section>
    </div>
  );
}
