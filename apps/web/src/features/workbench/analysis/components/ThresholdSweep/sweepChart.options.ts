import type { EChartsOption } from "echarts";

import type { ThresholdSweepPoint } from "@/features/workbench/analysis/api/compute";
import type { ChartTokens } from "@/lib/components/charts/chartTheme";
import { UNRESOLVED_SERIES_COLOR } from "@/lib/components/charts/unresolved";
import { fmtParamValue } from "../../utils/formatters";
import { truncateLabel } from "./types";

const CATEGORICAL_LABEL_MAX = 12;

export function formatSweepPercent(value: unknown): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "";
}

export function formatSweepAxisPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

export interface BuildSweepChartArgs {
  points: readonly ThresholdSweepPoint[];
  parameter: string;
  sweepType: "numeric" | "categorical";
  formatValue: (value: number | string) => string;
  tokens: ChartTokens;
}

export function buildSweepChartOption(args: BuildSweepChartArgs): EChartsOption {
  const sensitivity = args.tokens.series[0] ?? UNRESOLVED_SERIES_COLOR;
  const specificity = args.tokens.series[3] ?? UNRESOLVED_SERIES_COLOR;
  const harmonic = args.tokens.series[4] ?? UNRESOLVED_SERIES_COLOR;
  const gridLine = {
    lineStyle: { type: "dashed", color: args.tokens.border, opacity: 0.5 },
  } as const;

  return {
    animation: false,
    grid: { left: 56, right: 20, top: 30, bottom: 44 },
    xAxis: {
      type: "category",
      data: args.points.map((point) =>
        args.sweepType === "categorical"
          ? truncateLabel(args.formatValue(point.value), CATEGORICAL_LABEL_MAX)
          : fmtParamValue(Number(point.value)),
      ),
      name: args.parameter,
      nameLocation: "middle",
      nameGap: 26,
      axisLabel: { fontSize: 9 },
      axisTick: { show: false },
      splitLine: { show: true, ...gridLine },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      interval: 0.25,
      axisLabel: { fontSize: 9, formatter: formatSweepAxisPercent },
      splitLine: gridLine,
    },
    legend: { top: 0, right: 0, icon: "circle" },
    tooltip: { trigger: "axis", valueFormatter: formatSweepPercent },
    series: [
      {
        type: "line",
        name: "Sensitivity",
        data: args.points.map((point) => point.metrics?.sensitivity ?? 0),
        smooth: true,
        symbolSize: 6,
        itemStyle: { color: sensitivity },
        lineStyle: { color: sensitivity, width: 2 },
      },
      {
        type: "line",
        name: "Specificity",
        data: args.points.map((point) => point.metrics?.specificity ?? 0),
        smooth: true,
        symbolSize: 6,
        itemStyle: { color: specificity },
        lineStyle: { color: specificity, width: 2 },
      },
      {
        type: "line",
        name: "F1",
        data: args.points.map((point) => point.metrics?.f1Score ?? 0),
        smooth: true,
        symbolSize: 6,
        itemStyle: { color: harmonic },
        lineStyle: { color: harmonic, width: 2, type: [4, 2] },
      },
    ],
  };
}
