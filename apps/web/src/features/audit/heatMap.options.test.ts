import { describe, expect, it } from "vitest";

import { DISTINCT_CHART_TOKENS } from "@/lib/components/charts/__fixtures__/chartTokens";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { buildHeatOption, heatCells } from "./heatMap.options";

type HeatSeries = { type: string; data: [number, number, number | null][] };
type Tooltip = { formatter: (params: { dataIndex: number }) => string };

describe("the heat map's option", () => {
  it("lays each screened genome against each check, with the rate, its interval and the BUSCO gap", () => {
    const heat = heatCells(SAMPLE_RUN, SAMPLE_WORDS);
    expect(heat.genomes).toEqual([
      "Plasmodium falciparum Dd2 (BUSCO gap Not served by the site)",
      "Plasmodium falciparum NF54 (BUSCO gap Not served by the site)",
    ]);
    expect(heat.checks).toEqual(["gene_length", "pseudogene_call"]);
    expect(heat.cells).toHaveLength(4);
    const dd2 = heat.cells.find((cell) => cell.genome === 0 && cell.check === 0);
    expect([dd2?.share, dd2?.errors]).toEqual(["1 of 3", ["Model too short"]]);
    expect(dd2?.value).toBeCloseTo(1 / 3, 4);
    expect(
      heat.cells.find((cell) => cell.genome === 0 && cell.check === 1)?.value,
    ).toBe(null);
    const nf54 = heat.cells.find((cell) => cell.genome === 1 && cell.check === 1);
    expect(nf54?.errors).toEqual(["Intact gene called a pseudogene"]);
  });

  it("names no error another genome's model holds", () => {
    const counts = SAMPLE_RUN.counts.map((row) =>
      row.errorType === "truncated_model"
        ? { ...row, modelGenome: "Plasmodium falciparum 3D7" }
        : row,
    );
    const heat = heatCells({ ...SAMPLE_RUN, counts }, SAMPLE_WORDS);
    const dd2 = heat.cells.find((cell) => cell.genome === 0 && cell.check === 0);
    expect(dd2?.errors).toEqual([]);
  });

  it("draws a heat map whose empty cells say so", () => {
    const heat = heatCells(SAMPLE_RUN, SAMPLE_WORDS);
    const option = buildHeatOption(heat, SAMPLE_WORDS, DISTINCT_CHART_TOKENS);
    const [series] = option.series as HeatSeries[];
    expect(series?.type).toBe("heatmap");
    expect(series?.data.map(([check, genome]) => [check, genome])).toEqual(
      heat.cells.map((cell) => [cell.check, cell.genome]),
    );
    const tooltip = option.tooltip as Tooltip;
    const at = (genome: number, check: number) =>
      tooltip.formatter({
        dataIndex: heat.cells.findIndex(
          (cell) => cell.genome === genome && cell.check === check,
        ),
      });
    expect(at(0, 0)).toBe(
      "Plasmodium falciparum Dd2<br/>Gene length against orthologs<br/>33% (6% to 79%)<br/>1 of 3<br/>Model too short",
    );
    expect(at(0, 1)).toBe(
      "Plasmodium falciparum Dd2<br/>Pseudogene calls on intact genes<br/>No judged finding",
    );
  });
});
