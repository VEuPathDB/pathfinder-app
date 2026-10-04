import { describe, expect, it } from "vitest";

import { DISTINCT_CHART_TOKENS } from "./__fixtures__/chartTokens";
import { buildScatterOption } from "./scatter.options";

const args = {
  series: [
    {
      name: "Genes",
      x: [3.94437533216012, -2.5, 0.4],
      y: [4.708, 3, Number.POSITIVE_INFINITY],
      pointIds: ["PF3D7_0100200", "PF3D7_0100300", "PF3D7_0100400"],
    },
    { name: "Unlabelled", x: [-12.5], y: [3.5] },
  ],
  xAxis: { variableId: "effectSize", displayName: "log2(Fold Change)" },
  yAxis: { variableId: "pValue", displayName: "-log10(p-value)" },
  tokens: DISTINCT_CHART_TOKENS,
};

describe("buildScatterOption", () => {
  it("keeps each finite coordinate pair", () => {
    const option = buildScatterOption(args);
    expect(option.series[0]?.points[0]).toEqual([
      3.94437533216012,
      4.708,
      "PF3D7_0100200",
    ]);
  });

  it("labels a point with its own id when pointIds is present", () => {
    const option = buildScatterOption(args);
    expect(option.series[0]?.points[1]?.[2]).toBe("PF3D7_0100300");
  });

  it("falls back to the series name when pointIds is absent", () => {
    const option = buildScatterOption(args);
    expect(option.series[1]?.points[0]?.[2]).toBe("Unlabelled");
  });

  it("drops a point whose coordinate is not finite and counts it", () => {
    const option = buildScatterOption(args);
    expect(option.series[0]?.points).toHaveLength(2);
    expect(option.droppedPointCount).toBe(1);
  });

  it("drops a point whose x is not a number and counts it", () => {
    const option = buildScatterOption({
      ...args,
      series: [{ name: "Ragged x", x: [Number.NaN, 2], y: [1, 2] }],
    });
    expect(option.series[0]?.points).toEqual([[2, 2, "Ragged x"]]);
    expect(option.droppedPointCount).toBe(1);
  });

  it("stops at the shorter of x and y", () => {
    const option = buildScatterOption({
      ...args,
      series: [{ name: "Ragged", x: [1, 2, 3], y: [1] }],
    });
    expect(option.series[0]?.points).toHaveLength(1);
  });

  it("names the axes from the labels it is given", () => {
    const option = buildScatterOption(args);
    expect(option.xAxisName).toBe("log2(Fold Change)");
    expect(option.yAxisName).toBe("-log10(p-value)");
  });

  it("keeps the line's finite vertices in its own series, drawn in ink", () => {
    const option = buildScatterOption({
      ...args,
      line: {
        name: "Best-fit line",
        x: [0, 1, Number.NaN],
        y: [5.5487, 5.5713, 5.5939],
      },
    });
    expect(option.line).toEqual({
      name: "Best-fit line",
      points: [
        [0, 5.5487, "Best-fit line"],
        [1, 5.5713, "Best-fit line"],
      ],
      color: DISTINCT_CHART_TOKENS.foreground,
    });
  });

  it("counts a line vertex it leaves out as no dropped point", () => {
    const option = buildScatterOption({
      ...args,
      line: { name: "Best-fit line", x: [Number.NaN], y: [1] },
    });
    expect(option.droppedPointCount).toBe(1);
  });

  it("has no line when none is given", () => {
    expect(buildScatterOption(args).line).toBe(null);
  });

  it("colors series by token order", () => {
    const option = buildScatterOption(args);
    expect(option.series.map((s) => s.color)).toEqual([
      DISTINCT_CHART_TOKENS.series[0],
      DISTINCT_CHART_TOKENS.series[1],
    ]);
  });
});
