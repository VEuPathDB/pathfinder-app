import { describe, expect, it } from "vitest";

import { DISTINCT_CHART_TOKENS } from "./__fixtures__/chartTokens";
import { buildVolcanoOption, volcanoPointY } from "./volcano.options";
import { VOLCANO_POINT_SAMPLE } from "@/lib/eda/__fixtures__/volcanoSample";

const args = {
  points: VOLCANO_POINT_SAMPLE,
  thresholds: {
    effectSizeThreshold: 1,
    significanceThreshold: 0.05,
    direction: "upAndDown" as const,
  },
  effectSizeLabel: "log2(Fold Change)",
  tokens: DISTINCT_CHART_TOKENS,
};

describe("volcanoPointY", () => {
  it("is the negative base-ten log of the raw p-value", () => {
    expect(volcanoPointY(0.001)).toBeCloseTo(3, 12);
  });

  it("returns null for a zero p-value rather than Infinity", () => {
    expect(volcanoPointY(0)).toBe(null);
  });

  it("returns null when there is no p-value", () => {
    expect(volcanoPointY(undefined)).toBe(null);
  });

  it("returns null for an explicit null p-value", () => {
    expect(volcanoPointY(null)).toBe(null);
  });
});

describe("buildVolcanoOption", () => {
  it("plots three series: not-notable, up and down", () => {
    const option = buildVolcanoOption(args);
    expect(option.series.map((s) => s.name)).toEqual([
      "Not notable",
      "Higher in group B",
      "Higher in group A",
    ]);
  });

  it("names each side by its group's labels when the plot carries them", () => {
    const option = buildVolcanoOption({
      ...args,
      comparison: { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] },
    });
    expect(option.series.map((s) => s.name)).toEqual([
      "Not notable",
      "Higher in 18h pbm, 36h pbm",
      "Higher in 24h pbm",
    ]);
    expect(option.ariaLabel).toBe(
      "Volcano plot, Higher in 18h pbm, 36h pbm (2) and Higher in 24h pbm (1)",
    );
  });

  it("puts each qualifying gene in its own series with the right point count", () => {
    const option = buildVolcanoOption(args);
    expect(option.series.map((series) => series.data.map((point) => point[2]))).toEqual(
      [
        ["PF3D7_0100100", "PF3D7_0100500"],
        ["PF3D7_0100200", "PF3D7_0100400"],
        ["PF3D7_0100300"],
      ],
    );
  });

  it("carries the gene id on the point so the tooltip can name it", () => {
    const option = buildVolcanoOption(args);
    expect(option.series[1]?.data[0]?.[2]).toBe("PF3D7_0100200");
  });

  it("colors up with the positive token and down with the negative token", () => {
    const option = buildVolcanoOption(args);
    expect(option.series[1]?.itemStyle.color).toBe(DISTINCT_CHART_TOKENS.positive);
    expect(option.series[2]?.itemStyle.color).toBe(DISTINCT_CHART_TOKENS.negative);
  });

  it("draws three threshold guides: two effect-size and one significance", () => {
    const option = buildVolcanoOption(args);
    expect(option.thresholdLines).toEqual([
      { axis: "x", value: -1 },
      { axis: "x", value: 1 },
      { axis: "y", value: -Math.log10(0.05) },
    ]);
  });

  it("names the effect-size axis from the payload label", () => {
    const option = buildVolcanoOption(args);
    expect(option.xAxis.name).toBe("log2(Fold Change)");
  });

  it("drops a point whose effect size is not a number", () => {
    const option = buildVolcanoOption({
      ...args,
      points: [
        {
          pointId: "NAN",
          effectSize: Number.NaN,
          pValue: 0.001,
          adjustedPValue: 0.001,
        },
        { pointId: "OK", effectSize: 2, pValue: 0.001, adjustedPValue: 0.001 },
      ],
    });
    expect(option.droppedRowCount).toBe(1);
    expect(option.series[0]?.data).toEqual([]);
    expect(option.series[1]?.data.map((point) => point[2])).toEqual(["OK"]);
  });

  it("reports the point it could not plot", () => {
    const option = buildVolcanoOption(args);
    expect(option.droppedRowCount).toBe(1);
  });
});
