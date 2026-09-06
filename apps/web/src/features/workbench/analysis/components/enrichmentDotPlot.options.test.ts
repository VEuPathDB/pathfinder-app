import { describe, expect, it } from "vitest";
import type { EnrichmentTerm } from "@pathfinder/shared";

import { DISTINCT_CHART_TOKENS } from "@/lib/components/charts/__fixtures__/chartTokens";
import {
  buildEnrichmentDotPlot,
  dotPlotTooltip,
  formatDotPlotTooltip,
  readDotPlotPoint,
} from "./enrichmentDotPlot.options";

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

/** A stub ramp, so the option literal can name a colour without a DOM. */
const colorForPValue = (pValue: number | null): string =>
  pValue === null ? "hsl(0 0% 50%)" : `hsl(${String(pValue)})`;

function build(terms: EnrichmentTerm[]) {
  return buildEnrichmentDotPlot({
    terms,
    tokens: DISTINCT_CHART_TOKENS,
    colorForPValue,
  });
}

describe("buildEnrichmentDotPlot", () => {
  it("plots fold against the term axis and keeps an unbounded term label without a dot", () => {
    expect(build([term(), UNBOUNDED])).toEqual({
      maxGeneCount: 5,
      termCount: 2,
      height: 140,
      option: {
        animation: false,
        grid: { left: 208, right: 32, top: 8, bottom: 36 },
        xAxis: {
          type: "value",
          name: "Fold Enrichment",
          nameLocation: "middle",
          nameGap: 24,
          axisLabel: { fontSize: 10 },
          splitLine: {
            lineStyle: { type: "dashed", color: DISTINCT_CHART_TOKENS.border },
          },
        },
        yAxis: {
          type: "category",
          data: ["dna replication", "protein kinase activity"],
          axisLabel: { fontSize: 10 },
          axisLine: { show: false },
          axisTick: { show: false },
        },
        tooltip: { trigger: "item", formatter: dotPlotTooltip },
        series: [
          {
            type: "scatter",
            name: "Enriched terms",
            data: [
              {
                value: [3.48, "protein kinase activity", 3, 0.0001],
                symbolSize: 20,
                itemStyle: { color: "hsl(0.0001)", opacity: 0.85 },
              },
            ],
          },
        ],
      },
    });
  });

  it("orders the axis by ascending p-value and caps the plot at fifteen terms", () => {
    const many = Array.from({ length: 20 }, (_, index) =>
      term({
        termId: `GO:${String(index)}`,
        termName: `term-${String(index)}`,
        pValue: (index + 1) / 1000,
      }),
    );
    const model = build(many);

    expect(model.termCount).toBe(15);
    expect(model.option.yAxis).toEqual({
      type: "category",
      data: Array.from({ length: 15 }, (_, index) => `term-${String(14 - index)}`),
      axisLabel: { fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
    });
  });

  it("sizes the dot between the minimum and maximum radius by gene share", () => {
    const model = build([
      term({ termId: "a", termName: "a", geneCount: 10, pValue: 0.01 }),
      term({ termId: "b", termName: "b", geneCount: 0, pValue: 0.02 }),
    ]);

    expect(model.option.series).toEqual([
      {
        type: "scatter",
        name: "Enriched terms",
        data: [
          {
            value: [3.48, "b", 0, 0.02],
            symbolSize: 8,
            itemStyle: { color: "hsl(0.02)", opacity: 0.85 },
          },
          {
            value: [3.48, "a", 10, 0.01],
            symbolSize: 28,
            itemStyle: { color: "hsl(0.01)", opacity: 0.85 },
          },
        ],
      },
    ]);
  });

  it("grows the plot by one row height per term past the minimum", () => {
    expect(
      build(
        Array.from({ length: 8 }, (_, index) =>
          term({ termId: String(index), termName: `t-${String(index)}` }),
        ),
      ).height,
    ).toBe(264);
  });

  it("falls back to the term id and truncates a long label", () => {
    const model = build([
      term({ termId: "GO:0000001", termName: "", pValue: 0.001 }),
      term({ termId: "GO:0000002", termName: "a".repeat(40), pValue: 0.002 }),
    ]);

    expect(model.option.yAxis).toMatchObject({
      data: [`${"a".repeat(32)}...`, "GO:0000001"],
    });
  });
});

describe("readDotPlotPoint", () => {
  it("reads the [fold, term, genes, p] tuple a dot carries", () => {
    expect(readDotPlotPoint([3.48, "kinase", 3, 0.0001])).toEqual([
      3.48,
      "kinase",
      3,
      0.0001,
    ]);
  });

  it("accepts a null p-value", () => {
    expect(readDotPlotPoint([3.48, "kinase", 3, null])).toEqual([
      3.48,
      "kinase",
      3,
      null,
    ]);
  });

  it("refuses a tuple it cannot read as a dot", () => {
    const unreadable = [
      [],
      [3.48, 7, 3, 0.1],
      [3.48, "kinase", 3],
      [3.48, "kinase", 3, "0.1"],
    ];
    expect(unreadable.map(readDotPlotPoint)).toEqual([null, null, null, null]);
  });
});

describe("formatDotPlotTooltip", () => {
  it("names the term and reports the fold, gene count and p-value", () => {
    const text = formatDotPlotTooltip([3.48, "protein kinase activity", 3, 0.0001]);
    expect(text).toContain("protein kinase activity");
    expect(text).toContain("Fold: 3.48");
    expect(text).toContain("Genes: 3");
    expect(text).toContain("p: 1.00e-4");
  });

  it("reports a term with no p-value as not computable", () => {
    expect(formatDotPlotTooltip([2, "term", 4, null])).toContain("p: n/a");
  });
});
