// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { UNRESOLVED_SERIES_COLOR } from "@/lib/components/charts/unresolved";
import { SetVenn } from "./SetVenn";

// Mock reaviz — D3/SVG doesn't work in jsdom
vi.mock("reaviz", () => ({
  VennDiagram: ({
    data,
    type,
    series,
  }: {
    data: { key: string[]; data: number }[];
    type: string;
    series: React.ReactNode;
  }) => (
    <div data-testid="reaviz-venn" data-type={type} data-count={data.length}>
      {data.map((d: { key: string[]; data: number }) => (
        <span key={d.key.join(",")} data-testid={`venn-datum-${d.key.join(",")}`}>
          {d.data}
        </span>
      ))}
      {series}
    </div>
  ),
  VennSeries: ({ colorScheme }: { colorScheme: string[] }) => (
    <div data-testid="venn-series" data-colors={colorScheme.join(",")} />
  ),
  VennArc: () => <div />,
  VennLabel: () => <div />,
  ChartTooltip: () => <div />,
}));

afterEach(cleanup);

describe("SetVenn", () => {
  const twoSets = [
    { key: "Set A", geneIds: ["g1", "g2", "g3"] },
    { key: "Set B", geneIds: ["g2", "g3", "g4", "g5"] },
  ];

  it("renders reaviz VennDiagram with euler type", () => {
    render(<SetVenn sets={twoSets} />);
    const venn = screen.getByTestId("reaviz-venn");
    expect(venn.dataset["type"]).toBe("euler");
  });

  it("passes correct data count for 2 sets (3 entries)", () => {
    render(<SetVenn sets={twoSets} />);
    const venn = screen.getByTestId("reaviz-venn");
    expect(venn.dataset["count"]).toBe("3");
  });

  it("passes log-scaled data values (not raw counts) to reaviz", () => {
    render(<SetVenn sets={twoSets} />);
    // Raw: A=3, B=4, A∩B=2. Log-scaled: log(4)≈1.39, log(5)≈1.61, log(3)≈1.10
    const aVal = Number(screen.getByTestId("venn-datum-Set A").textContent);
    const bVal = Number(screen.getByTestId("venn-datum-Set B").textContent);
    const abVal = Number(screen.getByTestId("venn-datum-Set A,Set B").textContent);
    expect(aVal).toBeCloseTo(Math.log(4), 5);
    expect(bVal).toBeCloseTo(Math.log(5), 5);
    expect(abVal).toBeCloseTo(Math.log(3), 5);
    // Ordering preserved
    expect(bVal).toBeGreaterThan(aVal);
    expect(aVal).toBeGreaterThan(abVal);
  });

  it("renders 3-set data with 7 entries", () => {
    const threeSets = [
      { key: "X", geneIds: ["g1", "g2"] },
      { key: "Y", geneIds: ["g2", "g3"] },
      { key: "Z", geneIds: ["g3", "g4"] },
    ];
    render(<SetVenn sets={threeSets} />);
    const venn = screen.getByTestId("reaviz-venn");
    expect(venn.dataset["count"]).toBe("7");
  });

  it("renders instruction text when onRegionClick provided", () => {
    render(<SetVenn sets={twoSets} onRegionClick={vi.fn()} />);
    expect(screen.getByText("Click a region to create a gene set")).toBeTruthy();
  });

  it("does not render instruction text when no onRegionClick", () => {
    render(<SetVenn sets={twoSets} />);
    expect(screen.getByTestId("reaviz-venn")).toBeVisible();
    expect(screen.queryAllByText("Click a region to create a gene set")).toHaveLength(
      0,
    );
  });

  it("colors the arcs from the chart tokens on the document", () => {
    const root = document.documentElement;
    root.style.setProperty("--chart-1", "215 75% 45%");
    root.style.setProperty("--chart-2", "160 65% 33%");
    try {
      render(<SetVenn sets={twoSets} />);
      expect(screen.getByTestId("venn-series").dataset["colors"]).toBe(
        "hsl(215 75% 45%),hsl(160 65% 33%)",
      );
    } finally {
      root.removeAttribute("style");
    }
  });

  it("paints the unresolved neutral when the stylesheet defines nothing", () => {
    render(<SetVenn sets={twoSets} />);
    expect(screen.getByTestId("venn-series").dataset["colors"]).toBe(
      `${UNRESOLVED_SERIES_COLOR},${UNRESOLVED_SERIES_COLOR}`,
    );
  });
});

describe("SetVenn promises no diagram it cannot draw", () => {
  const withoutGenes = [
    { key: "Set A", geneIds: [] },
    { key: "Set B", geneIds: [] },
  ];

  it("draws no empty diagram and no click instruction for sets with no stored genes", () => {
    render(<SetVenn sets={withoutGenes} onRegionClick={vi.fn()} />);
    expect(screen.queryAllByTestId("reaviz-venn")).toHaveLength(0);
    expect(screen.queryAllByText("Click a region to create a gene set")).toHaveLength(
      0,
    );
  });

  it("says why instead", () => {
    render(<SetVenn sets={withoutGenes} onRegionClick={vi.fn()} />);
    expect(
      screen.getByText(
        "These gene sets store no gene IDs, so there is no overlap to draw.",
      ),
    ).toBeTruthy();
  });

  it("still draws when one of the two sets has genes", () => {
    render(
      <SetVenn
        sets={[
          { key: "Set A", geneIds: ["g1"] },
          { key: "Set B", geneIds: [] },
        ]}
      />,
    );
    expect(screen.getByTestId("reaviz-venn")).toBeTruthy();
  });
});

describe("SetVenn refuses a selection the layout cannot place", () => {
  const sameGenes = ["PF3D7_0102200", "PF3D7_0207600", "PF3D7_0208900"];
  const repeated = [
    { key: "gam positives", geneIds: ["PF3D7_0102200", "PF3D7_1133400"] },
    { key: "gametocyte secreted candidates", geneIds: sameGenes },
    { key: "gametocyte secreted candidates v2", geneIds: [...sameGenes].reverse() },
    { key: "gametocyte secreted candidates v3", geneIds: sameGenes },
  ];

  it("draws no diagram when three of the sets hold the same genes", () => {
    render(<SetVenn sets={repeated} onRegionClick={vi.fn()} />);
    expect(screen.queryAllByTestId("reaviz-venn")).toHaveLength(0);
    expect(screen.queryAllByText("Click a region to create a gene set")).toHaveLength(
      0,
    );
  });

  it("names the sets it cannot separate", () => {
    render(<SetVenn sets={repeated} />);
    expect(
      screen.getByText(
        "gametocyte secreted candidates, gametocyte secreted candidates v2, and " +
          "gametocyte secreted candidates v3 hold the same genes, so an overlap " +
          "diagram cannot separate them.",
      ),
    ).toBeVisible();
  });

  it("still draws a selection whose sets differ", () => {
    render(
      <SetVenn
        sets={[
          { key: "Set A", geneIds: ["g1", "g2", "g3"] },
          { key: "Set B", geneIds: ["g2", "g3", "g4"] },
          { key: "Set C", geneIds: ["g4", "g5"] },
        ]}
      />,
    );
    expect(screen.getByTestId("reaviz-venn")).toBeTruthy();
  });
});
