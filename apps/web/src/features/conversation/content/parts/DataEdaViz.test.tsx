/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render as renderBare,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import type { ReactElement, ReactNode } from "react";

import { useEdaStore } from "@/state/eda";
import {
  ChatHelpersProvider,
  type ChatHelpers,
} from "../../runtime/chatHelpersContext";
import { DataEdaViz } from "./DataEdaViz";
import {
  EDA_ANALYSIS_STATE_FIXTURE,
  EDA_SCATTER_VIZ_FIXTURE,
  EDA_VOLCANO_VIZ_FIXTURE,
} from "./edaPartFixtures";

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;

function ChatWrapper({ children }: { children: ReactNode }) {
  return <ChatHelpersProvider value={STUB_CHAT}>{children}</ChatHelpersProvider>;
}

function render(ui: ReactElement) {
  return renderBare(ui, { wrapper: ChatWrapper });
}

beforeEach(() => {
  useEdaStore.getState().reset();
  useEdaStore.getState().applyAnalysisState(EDA_ANALYSIS_STATE_FIXTURE);
});

describe("DataEdaViz volcano", () => {
  it("names the plot in the figure title and draws the volcano", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    const title = screen.getByText("log2(Fold Change)");
    expect(title.tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("eda-viz-volcano")).toHaveAttribute("role", "img");
  });

  it("names both groups of the comparison under the title", () => {
    render(
      <DataEdaViz
        data={{
          ...EDA_VOLCANO_VIZ_FIXTURE,
          comparison: { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] },
        }}
      />,
    );
    expect(screen.getByTestId("eda-viz-comparison").textContent).toBe(
      "Group A: 24h pbm - Group B: 18h pbm, 36h pbm",
    );
  });

  it("prints no comparison line for a plot that carries none", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.queryByTestId("eda-viz-comparison")).toBe(null);
    expect(screen.getByTestId("eda-viz-volcano").getAttribute("aria-label")).toMatch(
      /Higher in group B \(\d+\) and Higher in group A \(\d+\)$/,
    );
  });

  it("names each side of the volcano by its group's labels", () => {
    render(
      <DataEdaViz
        data={{
          ...EDA_VOLCANO_VIZ_FIXTURE,
          comparison: { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] },
        }}
      />,
    );
    expect(screen.getByTestId("eda-viz-volcano").getAttribute("aria-label")).toMatch(
      /Higher in 18h pbm, 36h pbm \(\d+\) and Higher in 24h pbm \(\d+\)$/,
    );
  });

  it("links the analysis in the site explorer the thread's state names", () => {
    const chat = {
      messages: [
        {
          id: "m-1",
          role: "assistant",
          parts: [
            {
              type: "data-eda.analysis-state",
              data: {
                ...EDA_ANALYSIS_STATE_FIXTURE,
                analysisUrl:
                  "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
              },
            },
          ],
        },
      ],
      status: "ready",
    } as unknown as ChatHelpers;
    renderBare(
      <ChatHelpersProvider value={chat}>
        <DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />
      </ChatHelpersProvider>,
    );
    const link = screen.getByRole("link", { name: "Open in PlasmoDB" });
    expect(link).toHaveAttribute(
      "href",
      "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1",
    );
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("offers no site link when the thread names no page for the analysis", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.queryByRole("link", { name: "Open in PlasmoDB" })).toBe(null);
  });

  it("captions the figure with the compute's retained count", () => {
    render(
      <DataEdaViz
        data={{ ...EDA_VOLCANO_VIZ_FIXTURE, totalPoints: 5511, retainedPoints: 1543 }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "1,543 of 5,511 genes retained.",
    );
  });

  it("draws no divider, no card and no outer margin", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-eda-viz").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });

  it("reports the client selection and the compute's own retained count", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    const line = screen.getByTestId("eda-viz-volcano-selection");
    expect(line).toHaveTextContent("1 gene selected");
    expect(line).toHaveTextContent("1 of 3 retained by the compute");
  });

  it("lists the selected gene beside the plot", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-volcano-genes")).toHaveTextContent(
      "PF3D7_0100200",
    );
  });

  it("holds the gene ids in a closed disclosure that counts them", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    const summary = screen.getByText("Gene ids (1)").closest("summary");
    expect(summary).not.toBeNull();
    const details = summary?.closest("details") ?? null;
    expect(details?.open).toBe(false);
    expect(details).toContainElement(screen.getByTestId("eda-viz-volcano-genes"));
  });

  it("keeps the selection readout outside the disclosure", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-volcano-selection").closest("details")).toBe(
      null,
    );
  });

  it("draws the plot expanded and collapses on request", async () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-volcano")).toHaveStyle({ height: "480px" });
    await userEvent.click(screen.getByRole("button", { name: "Collapse plot" }));
    expect(screen.getByTestId("eda-viz-volcano")).toHaveStyle({ height: "220px" });
    expect(screen.getByRole("button", { name: "Expand plot" })).toBeInTheDocument();
  });

  it("leads the caption with the sentence the model wrote", () => {
    render(
      <DataEdaViz
        data={{
          ...EDA_VOLCANO_VIZ_FIXTURE,
          totalPoints: 5511,
          retainedPoints: 1543,
          caption: "Genes higher in febrile samples than in normal samples",
        }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Genes higher in febrile samples than in normal samples (1,543 of 5,511 genes retained).",
    );
  });

  it("puts the caption above the selection readout and the gene ids", () => {
    const { container } = render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    const caption = screen.getByTestId("figure-caption");
    const readout = screen.getByTestId("eda-viz-volcano-selection");
    const genes = screen.getByTestId("eda-viz-volcano-genes");
    expect(container.contains(caption)).toBe(true);
    expect(
      caption.compareDocumentPosition(readout) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeGreaterThan(0);
    expect(
      caption.compareDocumentPosition(genes) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeGreaterThan(0);
  });

  it("keeps the plot itself above the caption", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    const caption = screen.getByTestId("figure-caption");
    const plot = screen.getByTestId("eda-viz-volcano");
    expect(
      caption.compareDocumentPosition(plot) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeGreaterThan(0);
  });

  it("hydrates the store so the tab shows the same plot", async () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    await waitFor(() => {
      expect(useEdaStore.getState().viz["volcano"]?.retainedPoints).toBe(1);
    });
  });

  it("reports the point it could not plot", () => {
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-volcano-dropped")).toHaveTextContent(
      "1 point without a p-value was not plotted",
    );
  });

  it("uses the thresholds the tab set, so both surfaces agree", () => {
    useEdaStore.getState().setVolcanoThresholds({
      effectSizeThreshold: 4,
      significanceThreshold: 0.05,
      direction: "upAndDown",
    });
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-volcano-selection")).toHaveTextContent(
      "0 genes selected",
    );
    expect(screen.queryByTestId("eda-viz-volcano-genes")).toBe(null);
  });
});

describe("DataEdaViz other charts", () => {
  it("draws the scatter and names both axes", () => {
    render(<DataEdaViz data={EDA_SCATTER_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-scatter")).toHaveAttribute(
      "aria-label",
      "Scatter plot of -log10(p-value) against log2(Fold Change), 2 points",
    );
  });

  it("counts the scatter points beside the plot", () => {
    render(<DataEdaViz data={EDA_SCATTER_VIZ_FIXTURE} />);
    expect(screen.getByTestId("eda-viz-scatter-count")).toHaveTextContent(
      "2 of 3 points plotted",
    );
  });

  it("puts the scatter count below the caption", () => {
    render(<DataEdaViz data={EDA_SCATTER_VIZ_FIXTURE} />);
    const caption = screen.getByTestId("figure-caption");
    const count = screen.getByTestId("eda-viz-scatter-count");
    expect(
      caption.compareDocumentPosition(count) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeGreaterThan(0);
  });

  it("drops a scatter point at p = 0 as well as one with no p-value", () => {
    render(
      <DataEdaViz
        data={{
          ...EDA_SCATTER_VIZ_FIXTURE,
          totalPoints: 4,
          points: [
            {
              pointId: "PF3D7_0100200",
              effectSize: 3.94437533216012,
              pValue: 1.95781599815607e-5,
              adjustedPValue: 0.000137772236907279,
              retained: true,
            },
            {
              pointId: "PF3D7_0100300",
              effectSize: -2.5,
              pValue: 0.001,
              adjustedPValue: 0.004,
              retained: true,
            },
            {
              pointId: "PF3D7_0100400",
              effectSize: 1.1,
              pValue: 0,
              adjustedPValue: 0,
              retained: true,
            },
            {
              pointId: "PF3D7_MIT04200",
              effectSize: -1.49447459261845,
              pValue: null,
              adjustedPValue: null,
              retained: false,
            },
          ],
        }}
      />,
    );
    expect(screen.getByTestId("eda-viz-scatter-count")).toHaveTextContent(
      "2 of 4 points plotted",
    );
    expect(screen.getByTestId("eda-viz-scatter")).toHaveAttribute(
      "aria-label",
      "Scatter plot of -log10(p-value) against log2(Fold Change), 2 points",
    );
    expect(screen.queryByTestId("eda-viz-scatter-dropped")).toBe(null);
  });

  it("says a bar plot cannot be drawn from a point cloud", () => {
    render(<DataEdaViz data={{ ...EDA_VOLCANO_VIZ_FIXTURE, chart: "bar" }} />);
    expect(screen.getByTestId("data-eda-viz-unsupported-chart")).toHaveTextContent(
      "bar plots are not available from this compute",
    );
  });

  it("says the same for a histogram and a boxplot", () => {
    const { unmount } = render(
      <DataEdaViz data={{ ...EDA_VOLCANO_VIZ_FIXTURE, chart: "histogram" }} />,
    );
    expect(screen.getByTestId("data-eda-viz-unsupported-chart")).toHaveTextContent(
      "histogram plots are not available from this compute",
    );
    unmount();
    render(<DataEdaViz data={{ ...EDA_VOLCANO_VIZ_FIXTURE, chart: "boxplot" }} />);
    expect(screen.getByTestId("data-eda-viz-unsupported-chart")).toHaveTextContent(
      "boxplot plots are not available from this compute",
    );
  });

  it("says so when the payload carries no points at all", () => {
    render(<DataEdaViz data={{ ...EDA_VOLCANO_VIZ_FIXTURE, points: [] }} />);
    expect(screen.getByTestId("data-eda-viz-empty")).toHaveTextContent(
      "This compute returned no points",
    );
    expect(screen.queryByTestId("eda-viz-volcano")).toBe(null);
  });
});

describe("the gene-id copy control", () => {
  it("copies every selected id, comma separated, without toggling the disclosure", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<DataEdaViz data={EDA_VOLCANO_VIZ_FIXTURE} />);

    const details = screen
      .getByTestId("eda-viz-copy-gene-ids")
      .closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByTestId("eda-viz-copy-gene-ids"));

    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = writeText.mock.calls[0]?.[0] as string;
    expect(copied.split(", ").length).toBeGreaterThan(0);
    for (const id of copied.split(", ")) {
      expect(id).toMatch(/^\S+$/);
    }
    expect(details.open).toBe(false);
    expect(await screen.findByLabelText("Copy gene ids")).toBeVisible();
  });
});
