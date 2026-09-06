// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import type { EnrichmentTerm } from "@pathfinder/shared";
import {
  compareNullableAsc,
  filterByPThreshold,
  formatProbability,
  formatRatio,
  pvalColor,
  pvalGradient,
} from "./enrichment-utils";

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

describe("formatRatio", () => {
  it("renders an unbounded ratio as Inf", () => {
    expect(formatRatio(null, 2)).toBe("Inf");
  });

  it("keeps the requested number of decimals for a finite ratio", () => {
    expect(formatRatio(3.4812, 2)).toBe("3.48");
    expect(formatRatio(3.4812, 3)).toBe("3.481");
  });
});

describe("formatProbability", () => {
  it("renders a probability that is not computable as n/a", () => {
    expect(formatProbability(null)).toBe("n/a");
  });

  it("renders a finite probability in scientific notation", () => {
    expect(formatProbability(0.0001)).toBe("1.00e-4");
  });
});

describe("compareNullableAsc", () => {
  it("sorts an unbounded ratio last when ascending, so descending puts it first", () => {
    const ratios: (number | null)[] = [2, null, 9.5, 0.25];
    expect([...ratios].sort(compareNullableAsc)).toEqual([0.25, 2, 9.5, null]);
    expect([...ratios].sort((a, b) => -compareNullableAsc(a, b))).toEqual([
      null,
      9.5,
      2,
      0.25,
    ]);
  });

  it("sorts a probability with no value last when ascending", () => {
    const probabilities: (number | null)[] = [0.04, null, 1e-9, 0.5];
    expect([...probabilities].sort(compareNullableAsc)).toEqual([
      1e-9,
      0.04,
      0.5,
      null,
    ]);
  });

  it("treats two missing values as equal", () => {
    expect(compareNullableAsc(null, null)).toBe(0);
  });
});

describe("filterByPThreshold", () => {
  it("drops a term whose p-value is not computable", () => {
    const terms = [term(), term({ termId: "GO:0000001", pValue: null })];
    expect(filterByPThreshold(terms, 1).map((t) => t.termId)).toEqual(["GO:0004672"]);
  });

  it("keeps terms at or below the threshold", () => {
    const terms = [term({ pValue: 0.05 }), term({ termId: "GO:0000002", pValue: 0.2 })];
    expect(filterByPThreshold(terms, 0.05).map((t) => t.pValue)).toEqual([0.05]);
  });
});

describe("pvalColor", () => {
  function setRamp(): void {
    const root = document.documentElement;
    root.style.setProperty("--chart-1", "215 75% 45%");
    root.style.setProperty("--chart-4", "355 70% 45%");
    root.style.setProperty("--muted-foreground", "215 16% 40%");
  }

  afterEach(() => document.documentElement.removeAttribute("style"));

  it("gives a term with no p-value the muted-foreground token", () => {
    setRamp();
    expect(pvalColor(null)).toBe("hsl(215 16% 40%)");
  });

  it("starts the ramp on the chart-1 token", () => {
    setRamp();
    expect(pvalColor(1)).toBe("hsl(215 75% 45%)");
  });

  it("ends the ramp on the chart-4 token", () => {
    setRamp();
    expect(pvalColor(1e-10)).toBe("hsl(355 70% 45%)");
  });

  it("follows the ground the document is on", () => {
    setRamp();
    document.documentElement.style.setProperty("--chart-4", "355 80% 70%");
    expect(pvalColor(1e-10)).toBe("hsl(355 80% 70%)");
  });

  it("inherits the surrounding ink when the stylesheet defines nothing", () => {
    expect(pvalColor(1e-10)).toBe("currentColor");
    expect(pvalColor(null)).toBe("currentColor");
  });
});

describe("pvalGradient", () => {
  afterEach(() => document.documentElement.removeAttribute("style"));

  it("ramps the legend between the same two tokens, in four stops", () => {
    const root = document.documentElement;
    root.style.setProperty("--chart-1", "215 75% 45%");
    root.style.setProperty("--chart-4", "355 70% 45%");
    expect(pvalGradient()).toBe(
      "linear-gradient(to right, hsl(215 75% 45%), hsl(261.67 73.33% 45%), " +
        "hsl(308.33 71.67% 45%), hsl(355 70% 45%))",
    );
  });
});
