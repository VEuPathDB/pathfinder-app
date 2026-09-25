"use client";

import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import type { EdaComparison } from "@pathfinder/shared/generated/types/EdaComparison";

import { EChart } from "./EChart";
import { readChartTokens } from "./chartTheme";
import { buildVolcanoOption } from "./volcano.options";
import type { VolcanoPointInput, VolcanoThresholds } from "./types";

/** Read the [effect, -log10(p), gene] tuple the volcano series carries. */
function volcanoTooltip(params: TooltipComponentFormatterCallbackParams): string {
  const entry = Array.isArray(params) ? params[0] : params;
  const value = entry?.value;
  if (!Array.isArray(value)) return "";
  const [effect, significance, pointId] = value;
  if (typeof effect !== "number" || typeof significance !== "number") return "";
  if (typeof pointId !== "string") return "";
  return `${pointId}<br/>effect ${effect.toFixed(3)}<br/>-log10(p) ${significance.toFixed(2)}`;
}

export interface VolcanoChartProps {
  points: readonly VolcanoPointInput[];
  thresholds: VolcanoThresholds;
  effectSizeLabel: string;
  height: number;
  testId: string;
  comparison?: EdaComparison | null | undefined;
}

export function VolcanoChart(props: VolcanoChartProps) {
  const tokens = readChartTokens();
  const model = buildVolcanoOption({
    points: props.points,
    thresholds: props.thresholds,
    effectSizeLabel: props.effectSizeLabel,
    tokens,
    comparison: props.comparison,
  });

  const option: EChartsOption = {
    animation: false,
    grid: { left: 56, right: 16, top: 24, bottom: 44 },
    xAxis: {
      type: "value",
      name: model.xAxis.name,
      nameLocation: "middle",
      nameGap: 26,
    },
    yAxis: {
      type: "value",
      name: model.yAxis.name,
      nameLocation: "middle",
      nameGap: 40,
    },
    legend: { top: 0, right: 0, icon: "circle" },
    tooltip: { trigger: "item", formatter: volcanoTooltip },
    dataZoom: [
      { type: "inside", xAxisIndex: 0 },
      { type: "inside", yAxisIndex: 0 },
    ],
    series: [
      ...model.series.map((s) => ({
        type: "scatter" as const,
        name: s.name,
        data: s.data,
        symbolSize: 4,
        large: true,
        largeThreshold: 2000,
        itemStyle: s.itemStyle,
      })),
      {
        type: "line" as const,
        name: "Thresholds",
        data: [],
        silent: true,
        markLine: {
          symbol: "none",
          label: { show: false },
          lineStyle: { color: tokens.border, type: "dashed" },
          data: model.thresholdLines.map((line) =>
            line.axis === "x" ? { xAxis: line.value } : { yAxis: line.value },
          ),
        },
      },
    ],
  };

  return (
    <div className="w-full">
      <EChart
        option={option}
        height={props.height}
        ariaLabel={model.ariaLabel}
        testId={props.testId}
      />
      {model.droppedRowCount > 0 && (
        <p
          data-testid={`${props.testId}-dropped`}
          className="mt-1 text-[11px] text-muted-foreground"
        >
          {model.droppedRowCount === 1
            ? "1 point without a p-value was not plotted"
            : `${model.droppedRowCount} points without a p-value were not plotted`}
        </p>
      )}
    </div>
  );
}
