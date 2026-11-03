import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import { format } from "echarts/core";
import type { CheckWords } from "@pathfinder/shared/generated/types/CheckWords";
import type { GenomeRate } from "@pathfinder/shared/generated/types/GenomeRate";

import type { ChartTokens } from "@/lib/components/charts/chartTheme";
import { UNRESOLVED_SERIES_COLOR } from "@/lib/components/charts/unresolved";

import { percent } from "./format";

export interface RateRow {
  label: string;
  rate: number;
  low: number;
  high: number;
}

export function rateRows(rates: readonly GenomeRate[], checks: CheckWords): RateRow[] {
  return rates.flatMap((row) =>
    row.bounds === null
      ? []
      : [
          {
            label: `${row.genome}: ${checks[row.check]}`,
            rate: row.bounds.rate,
            low: row.bounds.low,
            high: row.bounds.high,
          },
        ],
  );
}

export function rateRowText(row: RateRow): string {
  return `${percent(row.rate)} (${percent(row.low)} to ${percent(row.high)})`;
}

export function buildRateOption(
  rows: readonly RateRow[],
  tokens: ChartTokens,
): EChartsOption {
  const color = tokens.series[0] ?? UNRESOLVED_SERIES_COLOR;
  return {
    animation: false,
    grid: { left: 16, right: 24, top: 8, bottom: 32, containLabel: true },
    xAxis: {
      type: "value",
      min: 0,
      max: 1,
      axisLabel: { formatter: (value: number) => percent(value) },
    },
    yAxis: { type: "category", inverse: true, data: rows.map((row) => row.label) },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: TooltipComponentFormatterCallbackParams) => {
        const first = Array.isArray(params) ? params[0] : params;
        const row = first === undefined ? undefined : rows[first.dataIndex];
        return row === undefined
          ? ""
          : `${format.encodeHTML(row.label)}<br/>${rateRowText(row)}`;
      },
    },
    series: [
      {
        type: "bar",
        stack: "interval",
        silent: true,
        itemStyle: { color: "transparent" },
        data: rows.map((row) => row.low),
      },
      {
        type: "bar",
        stack: "interval",
        name: "95% interval",
        barWidth: 14,
        itemStyle: { color, opacity: 0.35 },
        data: rows.map((row) => row.high - row.low),
      },
      {
        type: "scatter",
        name: "Rate",
        symbol: "diamond",
        symbolSize: 12,
        itemStyle: { color: tokens.foreground },
        data: rows.map((row, index) => [row.rate, index]),
      },
    ],
  };
}
