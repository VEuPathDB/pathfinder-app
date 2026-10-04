"use client";

import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import { format } from "echarts/core";

import { EChart } from "./EChart";
import { readChartTokens } from "./chartTheme";
import { buildScatterOption } from "./scatter.options";
import type { EdaAxisLabel, EdaScatterSeries } from "./types";

export interface ScatterChartProps {
  series: readonly EdaScatterSeries[];
  line?: EdaScatterSeries;
  xAxis: EdaAxisLabel;
  yAxis: EdaAxisLabel;
  height: number;
  testId: string;
}

/** Read the [x, y, label] tuple a scatter series carries. */
function readPoint(
  params: TooltipComponentFormatterCallbackParams,
): [number, number, string] | null {
  const entry = Array.isArray(params) ? params[0] : params;
  const value = entry?.value;
  if (!Array.isArray(value)) return null;
  const [x, y, label] = value;
  if (typeof x !== "number" || typeof y !== "number") return null;
  if (typeof label !== "string") return null;
  return [x, y, label];
}

export function ScatterChart(props: ScatterChartProps) {
  const tokens = readChartTokens();
  const model = buildScatterOption({
    series: props.series,
    line: props.line,
    xAxis: props.xAxis,
    yAxis: props.yAxis,
    tokens,
  });

  const option: EChartsOption = {
    animation: false,
    grid: { left: 56, right: 16, top: 24, bottom: 44 },
    xAxis: {
      type: "value",
      name: model.xAxisName,
      nameLocation: "middle",
      nameGap: 26,
    },
    yAxis: {
      type: "value",
      name: model.yAxisName,
      nameLocation: "middle",
      nameGap: 40,
    },
    ...(model.series.length + (model.line === null ? 0 : 1) > 1
      ? { legend: { top: 0, right: 0, icon: "circle" } }
      : {}),
    tooltip: {
      trigger: "item",
      formatter: (params: TooltipComponentFormatterCallbackParams) => {
        const point = readPoint(params);
        if (point === null) return "";
        const [x, y, label] = point;
        return `${format.encodeHTML(label)}<br/>${model.xAxisName} ${String(x)}<br/>${model.yAxisName} ${String(y)}`;
      },
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0 },
      { type: "inside", yAxisIndex: 0 },
    ],
    series: [
      ...model.series.map((s) => ({
        type: "scatter" as const,
        name: s.name,
        data: s.points,
        symbolSize: 6,
        large: true,
        largeThreshold: 2000,
        itemStyle: { color: s.color, opacity: 0.75 },
      })),
      ...(model.line === null
        ? []
        : [
            {
              type: "line" as const,
              name: model.line.name,
              data: model.line.points,
              showSymbol: false,
              silent: true,
              itemStyle: { color: model.line.color },
              lineStyle: { color: model.line.color, width: 1.5 },
            },
          ]),
    ],
  };

  const plotted = model.series.reduce((total, s) => total + s.points.length, 0);

  return (
    <div className="w-full">
      <EChart
        option={option}
        height={props.height}
        ariaLabel={`Scatter plot of ${model.yAxisName} against ${model.xAxisName}, ${String(plotted)} points`}
        testId={props.testId}
      />
      {model.droppedPointCount > 0 && (
        <p
          data-testid={`${props.testId}-dropped`}
          className="mt-1 text-[11px] text-muted-foreground"
        >
          {model.droppedPointCount === 1
            ? "1 point with a missing coordinate was not plotted"
            : `${String(model.droppedPointCount)} points with a missing coordinate were not plotted`}
        </p>
      )}
    </div>
  );
}
