import type { EChartsOption } from "echarts";
import type { ExperimentMetrics } from "@pathfinder/shared";

import type { ChartTokens } from "@/lib/components/charts/chartTheme";

const AXIS_NAMES = [
  "Sensitivity",
  "Specificity",
  "Precision",
  "F1",
  "Bal. Acc.",
  "MCC",
];

const SERIES_NAME = "Classification metrics";

/** The six radar values. MCC is [-1, 1], so it folds onto the shared radius. */
export function radarValues(metrics: ExperimentMetrics): number[] {
  return [
    metrics.sensitivity,
    metrics.specificity,
    metrics.precision,
    metrics.f1Score,
    metrics.balancedAccuracy,
    Math.max(0, (metrics.mcc + 1) / 2),
  ];
}

export interface BuildMetricsRadarArgs {
  metrics: ExperimentMetrics;
  tokens: ChartTokens;
}

export function buildMetricsRadarOption(args: BuildMetricsRadarArgs): EChartsOption {
  const ink = args.tokens.foreground;
  return {
    animation: false,
    radar: {
      indicator: AXIS_NAMES.map((name) => ({ name, min: 0, max: 1 })),
      radius: "75%",
      splitNumber: 4,
      axisLine: { lineStyle: { color: args.tokens.border } },
      splitLine: { lineStyle: { color: args.tokens.border } },
      splitArea: { show: false },
      axisName: { color: args.tokens.mutedForeground, fontSize: 10 },
      axisLabel: { show: true, color: args.tokens.mutedForeground, fontSize: 9 },
    },
    series: [
      {
        type: "radar",
        name: SERIES_NAME,
        symbol: "none",
        data: [
          {
            name: SERIES_NAME,
            value: radarValues(args.metrics),
            itemStyle: { color: ink },
            lineStyle: { color: ink, width: 1.5 },
            areaStyle: { color: ink, opacity: 0.12 },
          },
        ],
      },
    ],
  };
}
