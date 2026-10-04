/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));
vi.mock("./echartsRegistry", () => ({
  initChart: () => ({
    setOption,
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { BoxplotChart } from "./BoxplotChart";
import {
  applyDistinctChartTokens,
  clearDistinctChartTokens,
  DISTINCT_CHART_TOKENS,
} from "./__fixtures__/chartTokens";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

const boxes = [
  {
    label: "delta-DHC mutant",
    lowerFence: 0,
    q1: 0,
    median: 1,
    q3: 4.5,
    upperFence: 6,
    mean: 61.1667,
    outlierCount: 4,
  },
  {
    label: "delta-LRR5 mutant",
    lowerFence: 0,
    q1: 0,
    median: 1,
    q3: 5.25,
    upperFence: 8,
    mean: null,
    outlierCount: 1,
  },
  {
    label: "wildtype",
    lowerFence: 0,
    q1: 1,
    median: 13.5,
    q3: 45.5,
    upperFence: 49,
    mean: 76.7083,
    outlierCount: 4,
  },
];

type BoxOption = {
  xAxis: { type: string; data: string[] };
  legend?: { data: string[] };
  tooltip: { formatter: (params: unknown) => string };
  series: {
    type: string;
    name: string;
    data: number[][];
    itemStyle: { color: string; borderColor?: string };
    silent?: boolean;
  }[];
};

async function option(): Promise<BoxOption> {
  setOption.mockClear();
  render(<BoxplotChart boxes={boxes} height={240} testId="eda-boxplot" />);
  await flush();
  return setOption.mock.calls[0]?.[0] as BoxOption;
}

beforeEach(applyDistinctChartTokens);
afterEach(clearDistinctChartTokens);

describe("BoxplotChart", () => {
  it("names every group on the category axis", async () => {
    const chart = await option();
    expect(chart.xAxis).toEqual({
      type: "category",
      data: ["delta-DHC mutant", "delta-LRR5 mutant", "wildtype"],
      axisTick: { show: false },
    });
  });

  it("draws each box from its fences, quartiles and median", async () => {
    const chart = await option();
    expect(chart.series[0]?.type).toBe("boxplot");
    expect(chart.series[0]?.data).toEqual([
      [0, 0, 1, 4.5, 6],
      [0, 0, 1, 5.25, 8],
      [0, 1, 13.5, 45.5, 49],
    ]);
    expect(chart.series[0]?.itemStyle.borderColor).toBe(
      DISTINCT_CHART_TOKENS.series[0],
    );
  });

  it("marks the mean of each group that has one, in ink", async () => {
    const chart = await option();
    expect(chart.series[1]?.type).toBe("scatter");
    expect(chart.series[1]?.data).toEqual([
      [0, 61.1667],
      [2, 76.7083],
    ]);
    expect(chart.series[1]?.itemStyle.color).toBe(DISTINCT_CHART_TOKENS.foreground);
    expect(chart.series[1]?.silent).toBe(true);
    expect(chart.legend?.data).toEqual(["Mean"]);
  });

  it("names the five numbers, the mean and the outliers in the tooltip", async () => {
    const chart = await option();
    expect(chart.tooltip.formatter({ dataIndex: 0 })).toBe(
      "delta-DHC mutant<br/>upper fence 6<br/>Q3 4.5<br/>median 1<br/>Q1 0<br/>lower fence 0<br/>mean 61.1667<br/>4 outliers",
    );
  });

  it("leaves the mean out of the tooltip of a group without one", async () => {
    const chart = await option();
    expect(chart.tooltip.formatter({ dataIndex: 1 })).toBe(
      "delta-LRR5 mutant<br/>upper fence 8<br/>Q3 5.25<br/>median 1<br/>Q1 0<br/>lower fence 0<br/>1 outlier",
    );
  });

  it("escapes the group label it writes into the tooltip", async () => {
    setOption.mockClear();
    render(
      <BoxplotChart
        boxes={[
          {
            label: "<b>wildtype</b>",
            lowerFence: 0,
            q1: 0,
            median: 1,
            q3: 5.25,
            upperFence: 8,
            mean: null,
            outlierCount: 0,
          },
        ]}
        height={240}
        testId="eda-boxplot"
      />,
    );
    await flush();
    const chart = setOption.mock.calls[0]?.[0] as BoxOption;
    expect(chart.tooltip.formatter({ dataIndex: 0 })).toBe(
      "&lt;b&gt;wildtype&lt;/b&gt;<br/>upper fence 8<br/>Q3 5.25<br/>median 1<br/>Q1 0<br/>lower fence 0<br/>0 outliers",
    );
    expect("legend" in chart).toBe(false);
  });

  it("names the groups in its accessible label", () => {
    const { getByTestId } = render(
      <BoxplotChart boxes={boxes} height={240} testId="eda-boxplot" />,
    );
    expect(getByTestId("eda-boxplot")).toHaveAttribute(
      "aria-label",
      "Box plot of 3 groups: delta-DHC mutant, delta-LRR5 mutant, wildtype",
    );
    expect(getByTestId("eda-boxplot")).toHaveStyle({ height: "240px" });
  });
});
