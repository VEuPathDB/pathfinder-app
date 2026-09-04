import { describe, expect, it } from "vitest";
import type { ThresholdSweepPoint } from "@/features/analysis/api/compute";

import { DISTINCT_CHART_TOKENS } from "@/lib/components/charts/__fixtures__/chartTokens";
import {
  buildSweepChartOption,
  formatSweepAxisPercent,
  formatSweepPercent,
} from "./sweepChart.options";

function point(value: number | string, sensitivity: number): ThresholdSweepPoint {
  return {
    value,
    metrics: {
      sensitivity,
      specificity: 0.4,
      precision: 0.5,
      f1Score: 0.6,
      mcc: 0.3,
      balancedAccuracy: 0.65,
      totalResults: 100,
      falsePositiveRate: 0.6,
    },
  };
}

const SERIES_1 = DISTINCT_CHART_TOKENS.series[0];
const SERIES_4 = DISTINCT_CHART_TOKENS.series[3];
const SERIES_5 = DISTINCT_CHART_TOKENS.series[4];
const GRID = {
  lineStyle: { type: "dashed", color: DISTINCT_CHART_TOKENS.border, opacity: 0.5 },
};

describe("buildSweepChartOption", () => {
  it("draws the three metric lines over the numeric parameter values", () => {
    expect(
      buildSweepChartOption({
        points: [point(1, 0.9), { value: 2.5, metrics: null }],
        parameter: "min_gene_count",
        sweepType: "numeric",
        formatValue: String,
        tokens: DISTINCT_CHART_TOKENS,
      }),
    ).toEqual({
      animation: false,
      grid: { left: 56, right: 20, top: 30, bottom: 44 },
      xAxis: {
        type: "category",
        data: ["1", "2.50"],
        name: "min_gene_count",
        nameLocation: "middle",
        nameGap: 26,
        axisLabel: { fontSize: 9 },
        axisTick: { show: false },
        splitLine: { show: true, ...GRID },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        interval: 0.25,
        axisLabel: { fontSize: 9, formatter: formatSweepAxisPercent },
        splitLine: GRID,
      },
      legend: { top: 0, right: 0, icon: "circle" },
      tooltip: { trigger: "axis", valueFormatter: formatSweepPercent },
      series: [
        {
          type: "line",
          name: "Sensitivity",
          data: [0.9, 0],
          smooth: true,
          symbolSize: 6,
          itemStyle: { color: SERIES_1 },
          lineStyle: { color: SERIES_1, width: 2 },
        },
        {
          type: "line",
          name: "Specificity",
          data: [0.4, 0],
          smooth: true,
          symbolSize: 6,
          itemStyle: { color: SERIES_4 },
          lineStyle: { color: SERIES_4, width: 2 },
        },
        {
          type: "line",
          name: "F1",
          data: [0.6, 0],
          smooth: true,
          symbolSize: 6,
          itemStyle: { color: SERIES_5 },
          lineStyle: { color: SERIES_5, width: 2, type: [4, 2] },
        },
      ],
    });
  });

  it("truncates a categorical label so the axis stays readable", () => {
    const option = buildSweepChartOption({
      points: [point("protein kinase activity", 0.9)],
      parameter: "go_term",
      sweepType: "categorical",
      formatValue: String,
      tokens: DISTINCT_CHART_TOKENS,
    });

    expect(option.xAxis).toMatchObject({ data: ["protein kin…"] });
  });
});

describe("formatSweepPercent", () => {
  it("reports a metric to one decimal place", () => {
    expect(formatSweepPercent(0.8333)).toBe("83.3%");
  });

  it("reports nothing for a value that is not a number", () => {
    expect(formatSweepPercent("high")).toBe("");
  });
});

describe("formatSweepAxisPercent", () => {
  it("reports an axis tick as a whole percentage", () => {
    expect(formatSweepAxisPercent(0.25)).toBe("25%");
    expect(formatSweepAxisPercent(1)).toBe("100%");
  });
});
