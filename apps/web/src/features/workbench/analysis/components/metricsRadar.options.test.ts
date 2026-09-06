import { describe, expect, it } from "vitest";
import type { ExperimentMetrics } from "@pathfinder/shared";

import { DISTINCT_CHART_TOKENS } from "@/lib/components/charts/__fixtures__/chartTokens";
import { buildMetricsRadarOption, radarValues } from "./metricsRadar.options";

function metrics(overrides: Partial<ExperimentMetrics> = {}): ExperimentMetrics {
  return {
    confusionMatrix: {
      truePositives: 30,
      falsePositives: 20,
      trueNegatives: 100,
      falseNegatives: 10,
    },
    sensitivity: 0.75,
    specificity: 0.8333,
    precision: 0.6,
    f1Score: 0.6667,
    mcc: 0.5455,
    balancedAccuracy: 0.7917,
    ...overrides,
  };
}

const INK = DISTINCT_CHART_TOKENS.foreground;

describe("buildMetricsRadarOption", () => {
  it("builds the six-axis radar in the token ink", () => {
    expect(
      buildMetricsRadarOption({ metrics: metrics(), tokens: DISTINCT_CHART_TOKENS }),
    ).toEqual({
      animation: false,
      radar: {
        indicator: [
          { name: "Sensitivity", min: 0, max: 1 },
          { name: "Specificity", min: 0, max: 1 },
          { name: "Precision", min: 0, max: 1 },
          { name: "F1", min: 0, max: 1 },
          { name: "Bal. Acc.", min: 0, max: 1 },
          { name: "MCC", min: 0, max: 1 },
        ],
        radius: "75%",
        splitNumber: 4,
        axisLine: { lineStyle: { color: DISTINCT_CHART_TOKENS.border } },
        splitLine: { lineStyle: { color: DISTINCT_CHART_TOKENS.border } },
        splitArea: { show: false },
        axisName: { color: DISTINCT_CHART_TOKENS.mutedForeground, fontSize: 10 },
        axisLabel: {
          show: true,
          color: DISTINCT_CHART_TOKENS.mutedForeground,
          fontSize: 9,
        },
      },
      series: [
        {
          type: "radar",
          name: "Classification metrics",
          symbol: "none",
          data: [
            {
              name: "Classification metrics",
              value: [0.75, 0.8333, 0.6, 0.6667, 0.7917, 0.77275],
              itemStyle: { color: INK },
              lineStyle: { color: INK, width: 1.5 },
              areaStyle: { color: INK, opacity: 0.12 },
            },
          ],
        },
      ],
    });
  });
});

describe("radarValues", () => {
  it("keeps the five [0, 1] metrics as they are", () => {
    expect(radarValues(metrics()).slice(0, 5)).toEqual([
      0.75, 0.8333, 0.6, 0.6667, 0.7917,
    ]);
  });

  it("maps MCC from [-1, 1] onto the shared [0, 1] radius", () => {
    expect(radarValues(metrics({ mcc: 0 }))[5]).toBe(0.5);
    expect(radarValues(metrics({ mcc: 1 }))[5]).toBe(1);
    expect(radarValues(metrics({ mcc: -1 }))[5]).toBe(0);
  });
});
