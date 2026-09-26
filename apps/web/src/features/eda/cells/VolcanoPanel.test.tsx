/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { EdaViz } from "@pathfinder/shared";

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { useEdaStore } from "@/state/eda";
import { VolcanoPanel } from "./VolcanoPanel";

const KEPT = 4402;
const PLOTTED = 4000;
const IDS = Array.from(
  { length: KEPT },
  (_, index) => `AAEL${String(index).padStart(6, "0")}`,
);

const CAPPED: EdaViz = {
  datasetId: "DS_vb_dhc",
  analysisId: "a-1",
  chart: "volcano",
  effectSizeLabel: "log2(Fold Change)",
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  effectDirection: "upAndDown",
  totalPoints: 6603,
  retainedPoints: KEPT,
  retainedPointIds: IDS,
  points: IDS.slice(0, PLOTTED).map((pointId) => ({
    pointId,
    effectSize: 2,
    pValue: 0.001,
    adjustedPValue: 0.01,
    retained: true,
  })),
};

beforeEach(() => {
  useEdaStore.getState().reset();
});

describe("VolcanoPanel past the plot cap", () => {
  it("counts every retained gene at the plot's own cut", () => {
    render(<VolcanoPanel payload={CAPPED} />);
    expect(screen.getByTestId("eda-volcano-selection").textContent).toBe(
      "4402 genes selected, 4402 of 6603 retained by the comparison",
    );
    expect(screen.getByTestId("eda-volcano-readout-cap").textContent).toMatch(
      /of 4402 selected genes are listed\.$/,
    );
  });

  it("reads the plotted points at another cut", () => {
    useEdaStore.setState({
      volcanoThresholds: {
        effectSizeThreshold: 3,
        significanceThreshold: 0.05,
        direction: "upAndDown",
      },
    });
    render(<VolcanoPanel payload={CAPPED} />);
    expect(screen.getByTestId("eda-volcano-selection").textContent).toBe(
      "0 genes selected, 4402 of 6603 retained by the comparison",
    );
  });
});
