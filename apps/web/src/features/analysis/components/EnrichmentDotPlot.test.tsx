/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { EnrichmentTerm } from "@pathfinder/shared";

const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));
vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption,
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { EnrichmentDotPlot } from "./EnrichmentDotPlot";
import { pvalGradient } from "./enrichment-utils";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

function term(overrides: Partial<EnrichmentTerm> = {}): EnrichmentTerm {
  return {
    termId: "GO:0004672",
    termName: "protein kinase activity",
    geneCount: 3,
    backgroundCount: 120,
    foldEnrichment: 3.48,
    oddsRatio: 4.12,
    pValue: 0.0001,
    fdr: 0.002,
    bonferroni: 0.005,
    genes: [],
    ...overrides,
  };
}

const UNBOUNDED = term({
  termId: "GO:0006260",
  termName: "dna replication",
  geneCount: 5,
  foldEnrichment: null,
  pValue: 0.002,
});

type DotOption = {
  yAxis: { data: string[] };
  series: { data: { value: unknown[]; symbolSize: number }[] }[];
};

async function optionFor(terms: EnrichmentTerm[]): Promise<DotOption> {
  setOption.mockClear();
  render(<EnrichmentDotPlot terms={terms} />);
  await flush();
  return setOption.mock.calls[0]?.[0] as DotOption;
}

beforeEach(() => {
  setOption.mockClear();
});
afterEach(cleanup);

describe("EnrichmentDotPlot", () => {
  it("keeps the axis label of an unbounded term but draws no dot for it", async () => {
    const option = await optionFor([term(), UNBOUNDED]);

    expect(option.yAxis.data).toContain("dna replication");
    expect(option.series[0]?.data.map((d) => d.value[1])).toEqual([
      "protein kinase activity",
    ]);
  });

  it("sizes the dot from the gene count of the largest term", async () => {
    const option = await optionFor([term(), UNBOUNDED]);

    // 3 of the 5 genes of the largest term: 2 * (4 + 0.6 * (14 - 4)).
    expect(option.series[0]?.data[0]?.symbolSize).toBe(20);
  });

  it("renders an accessible chart region and names the term count", async () => {
    render(<EnrichmentDotPlot terms={[term(), UNBOUNDED]} />);
    await flush();

    expect(screen.getByTestId("enrichment-dot-plot")).toHaveAttribute("role", "img");
    expect(screen.getByText("Top 2 Terms by Significance")).toBeTruthy();
  });

  it("ramps the legend swatch from the chart tokens", () => {
    const root = document.documentElement;
    root.style.setProperty("--chart-1", "215 75% 45%");
    root.style.setProperty("--chart-4", "355 70% 45%");
    try {
      render(<EnrichmentDotPlot terms={[term()]} />);
      const swatch = screen.getByText("-log10(p)").previousElementSibling;
      expect(swatch).toHaveStyle({ background: pvalGradient() });
      const light = swatch?.getAttribute("style");
      cleanup();

      root.style.setProperty("--chart-1", "210 90% 70%");
      root.style.setProperty("--chart-4", "355 80% 70%");
      render(<EnrichmentDotPlot terms={[term()]} />);
      const darkSwatch = screen.getByText("-log10(p)").previousElementSibling;
      expect(darkSwatch).toHaveStyle({ background: pvalGradient() });
      expect(darkSwatch?.getAttribute("style")).not.toBe(light);
    } finally {
      root.removeAttribute("style");
    }
  });
});
