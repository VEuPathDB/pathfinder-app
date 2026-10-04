"use client";

import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import { format } from "echarts/core";
import type { EdaBoxplotBox } from "@pathfinder/shared/generated/types/EdaBoxplotBox";

import { EChart } from "./EChart";
import { readChartTokens } from "./chartTheme";
import { UNRESOLVED_SERIES_COLOR } from "./unresolved";

export interface BoxplotChartProps {
  boxes: readonly EdaBoxplotBox[];
  height: number;
  testId: string;
}

const MEAN = "Mean";

/** The five numbers, the mean and the outlier count of one group, one per line. */
function boxTooltip(box: EdaBoxplotBox): string {
  return [
    format.encodeHTML(box.label),
    `upper fence ${String(box.upperFence)}`,
    `Q3 ${String(box.q3)}`,
    `median ${String(box.median)}`,
    `Q1 ${String(box.q1)}`,
    `lower fence ${String(box.lowerFence)}`,
    ...(box.mean === null ? [] : [`mean ${String(box.mean)}`]),
    `${String(box.outlierCount)} ${box.outlierCount === 1 ? "outlier" : "outliers"}`,
  ].join("<br/>");
}

export function BoxplotChart(props: BoxplotChartProps) {
  const tokens = readChartTokens();
  const labels = props.boxes.map((box) => box.label);
  const means = props.boxes.flatMap((box, index) =>
    box.mean === null ? [] : [[index, box.mean]],
  );

  const option: EChartsOption = {
    animation: false,
    grid: { left: 56, right: 16, top: 24, bottom: 40 },
    xAxis: { type: "category", data: labels, axisTick: { show: false } },
    yAxis: { type: "value" },
    ...(means.length > 0 ? { legend: { top: 0, right: 0, data: [MEAN] } } : {}),
    tooltip: {
      trigger: "item",
      formatter: (params: TooltipComponentFormatterCallbackParams) => {
        const entry = Array.isArray(params) ? params[0] : params;
        const box = entry === undefined ? undefined : props.boxes[entry.dataIndex];
        return box === undefined ? "" : boxTooltip(box);
      },
    },
    series: [
      {
        type: "boxplot",
        name: "Groups",
        data: props.boxes.map((box) => [
          box.lowerFence,
          box.q1,
          box.median,
          box.q3,
          box.upperFence,
        ]),
        itemStyle: {
          color: tokens.card,
          borderColor: tokens.series[0] ?? UNRESOLVED_SERIES_COLOR,
        },
      },
      {
        type: "scatter",
        name: MEAN,
        data: means,
        symbol: "diamond",
        symbolSize: 8,
        silent: true,
        itemStyle: { color: tokens.foreground },
      },
    ],
  };

  return (
    <EChart
      option={option}
      height={props.height}
      ariaLabel={`Box plot of ${String(labels.length)} ${labels.length === 1 ? "group" : "groups"}: ${labels.join(", ")}`}
      testId={props.testId}
    />
  );
}
