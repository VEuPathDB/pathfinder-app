/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
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

import { VolcanoChart } from "./VolcanoChart";
import { VOLCANO_POINT_SAMPLE } from "@/lib/eda/__fixtures__/volcanoSample";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

const props = {
  points: VOLCANO_POINT_SAMPLE,
  thresholds: {
    effectSizeThreshold: 1,
    significanceThreshold: 0.05,
    direction: "upAndDown" as const,
  },
  effectSizeLabel: "log2(Fold Change)",
  height: 280,
  testId: "eda-viz-volcano",
};

describe("VolcanoChart", () => {
  it("hands ECharts three scatter series and one mark-line series", async () => {
    render(<VolcanoChart {...props} />);
    await flush();
    const option = setOption.mock.calls[0]?.[0] as {
      series: { type: string; name: string }[];
    };
    expect(option.series.map((s) => s.type)).toEqual([
      "scatter",
      "scatter",
      "scatter",
      "line",
    ]);
    expect(option.series[3]?.name).toBe("Thresholds");
  });

  it("names the gene and both coordinates in the point tooltip", async () => {
    render(<VolcanoChart {...props} />);
    await flush();
    const option = setOption.mock.calls[0]?.[0] as {
      tooltip: { formatter: (params: unknown) => string };
    };
    expect(
      option.tooltip.formatter({ value: [3.94437533216012, 3.8607, "PF3D7_0100200"] }),
    ).toBe("PF3D7_0100200<br/>effect 3.944<br/>-log10(p) 3.86");
  });

  it("says how many points it could not plot", () => {
    const { getByTestId } = render(<VolcanoChart {...props} />);
    expect(getByTestId("eda-viz-volcano-dropped")).toHaveTextContent(
      "1 point without a p-value was not plotted",
    );
  });
});
