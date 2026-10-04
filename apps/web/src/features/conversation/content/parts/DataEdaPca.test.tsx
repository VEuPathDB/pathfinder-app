/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render as renderBare, screen } from "@testing-library/react";

const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));
vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption,
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import type { ReactElement, ReactNode } from "react";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataEdaPca } from "./DataEdaPca";
import { EDA_ANALYSIS_STATE_FIXTURE, EDA_PCA_FIXTURE } from "./edaPartFixtures";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

type ScatterOption = {
  legend?: object;
  series: { name: string; data: [number, number, string][] }[];
};

function render(
  ui: ReactElement,
  parts = [threadPart("data-eda.pca", EDA_PCA_FIXTURE)],
) {
  const chat = chatHelpersFor(threadOf(parts));
  function Wrapper({ children }: { children: ReactNode }) {
    return <ChatHelpersProvider value={chat}>{children}</ChatHelpersProvider>;
  }
  return renderBare(ui, { wrapper: Wrapper });
}

describe("DataEdaPca", () => {
  it("names both axes by their components and their variance", () => {
    render(<DataEdaPca data={EDA_PCA_FIXTURE} />);
    expect(screen.getByTestId("eda-pca-scatter")).toHaveAttribute(
      "aria-label",
      "Scatter plot of PC 2 (12.79% variance) against PC 1 (54.35% variance), 12 points",
    );
  });

  it("draws one series per group, each point labelled by its sample", async () => {
    setOption.mockClear();
    render(<DataEdaPca data={EDA_PCA_FIXTURE} />);
    await flush();
    const option = setOption.mock.calls[0]?.[0] as ScatterOption;
    expect(option.series.map((s) => s.name)).toEqual([
      "delta-DHC mutant",
      "delta-LRR5 mutant",
      "wildtype",
    ]);
    expect(option.series[2]?.data[0]).toEqual([
      -7.2548330125957,
      -19.2972293300329,
      "WT_37C_Rep1",
    ]);
    expect(option.legend).toEqual({ top: 0, right: 0, icon: "circle" });
  });

  it("titles the figure and numbers it among the thread's plots", () => {
    render(<DataEdaPca data={EDA_PCA_FIXTURE} />);
    expect(
      screen.getByText("Principal component analysis").closest("figcaption")?.tagName,
    ).toBe("FIGCAPTION");
    expect(screen.getByTestId("figure")).toHaveAttribute("id", "figure-1");
  });

  it("captions the plot with the model's sentence, the samples and the groups", () => {
    render(<DataEdaPca data={EDA_PCA_FIXTURE} />);
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      "Figure 1. The samples separate by temperature along the first component (12 samples, 3 groups).",
    );
  });

  it("names the study in the caption when the thread holds its state", () => {
    render(<DataEdaPca data={EDA_PCA_FIXTURE} />, [
      threadPart("data-eda.analysis-state", EDA_ANALYSIS_STATE_FIXTURE),
      threadPart("data-eda.pca", EDA_PCA_FIXTURE),
    ]);
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      "(Heat shock response in sensitive mutants (LRR5, DHC) - 12 samples, 3 groups).",
    );
  });

  it("counts one sample and one group in the singular", () => {
    const single = {
      ...EDA_PCA_FIXTURE,
      caption: "",
      series: [{ label: "wildtype", x: [1], y: [2], sampleIds: ["WT_37C_Rep1"] }],
      sampleCount: 1,
      groupCount: 1,
    };
    render(<DataEdaPca data={single} />, [threadPart("data-eda.pca", single)]);
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      "Figure 1. 1 sample, 1 group.",
    );
  });

  it("shows the stale-part notice for a reduction with one axis", () => {
    render(
      <DataEdaPca
        data={{ ...EDA_PCA_FIXTURE, axes: EDA_PCA_FIXTURE.axes.slice(0, 1) }}
      />,
    );
    expect(screen.getByTestId("stale-part-notice")).toHaveTextContent(
      "A plot from an earlier version of PathFinder can't be shown.",
    );
    expect(screen.queryByTestId("data-eda-pca")).toBe(null);
  });
});
