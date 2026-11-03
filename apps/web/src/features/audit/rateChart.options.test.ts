import { describe, expect, it } from "vitest";

import { DISTINCT_CHART_TOKENS } from "@/lib/components/charts/__fixtures__/chartTokens";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { buildRateOption, rateRows } from "./rateChart.options";

describe("the rate chart's option", () => {
  it("draws each sampled rate as its interval and a mark at the rate", () => {
    const rows = rateRows(SAMPLE_RUN.rates, SAMPLE_WORDS.checks);
    expect(rows.map((row) => row.label)).toEqual([
      "Plasmodium falciparum Dd2: Gene length against orthologs",
      "Plasmodium falciparum NF54: Pseudogene calls on intact genes",
    ]);
    expect(rows[0]?.rate).toBeCloseTo(1 / 3, 4);
    expect(rows[0]?.low).toBeCloseTo(0.0615, 3);
    expect(rows[0]?.high).toBeCloseTo(0.7923, 3);
    expect(rows[1]?.low).toBeCloseTo(0.2065, 3);
    const option = buildRateOption(rows, DISTINCT_CHART_TOKENS);
    const [base, interval, mark] = option.series as [
      { data: number[] },
      { data: number[] },
      { data: [number, number][] },
    ];
    expect(base.data[0]).toBeCloseTo(0.0615, 3);
    expect(interval.data[0]).toBeCloseTo(0.7923 - 0.0615, 3);
    expect(mark.data.map(([, row]) => row)).toEqual([0, 1]);
    expect(mark.data[0]?.[0]).toBeCloseTo(1 / 3, 4);
  });

  it("states a row's numbers in its tooltip and encodes the site's text", () => {
    const [row] = rateRows(SAMPLE_RUN.rates, SAMPLE_WORDS.checks);
    if (row === undefined) throw new Error("the sample run holds rates");
    const option = buildRateOption(
      [{ ...row, label: "<b>genome</b>" }],
      DISTINCT_CHART_TOKENS,
    );
    const tooltip = option.tooltip as {
      formatter: (params: { dataIndex: number }[]) => string;
    };
    expect(tooltip.formatter([{ dataIndex: 0 }])).toBe(
      "&lt;b&gt;genome&lt;/b&gt;<br/>33% (6% to 79%), 1 of 3",
    );
  });

  it("leaves out a check with no judged finding", () => {
    const rate = SAMPLE_RUN.rates.map((row) => ({ ...row, bounds: null }));
    expect(rateRows(rate, SAMPLE_WORDS.checks)).toEqual([]);
  });
});
