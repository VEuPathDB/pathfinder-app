/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { EnrichmentTerm } from "@pathfinder/shared";
import { useEnrichmentTableState } from "./useEnrichmentTableState";

function term(overrides: Partial<EnrichmentTerm> = {}): EnrichmentTerm {
  return {
    termId: "GO:0000001",
    termName: "term one",
    geneCount: 3,
    backgroundCount: 120,
    foldEnrichment: 2,
    oddsRatio: 2,
    pValue: 0.01,
    fdr: 0.02,
    bonferroni: 0.03,
    genes: [],
    ...overrides,
  };
}

const TERMS: EnrichmentTerm[] = [
  term({ termId: "finite", foldEnrichment: 9.5, pValue: 0.01, fdr: 0.02 }),
  term({ termId: "unbounded", foldEnrichment: null, pValue: 0.2, fdr: null }),
  term({ termId: "weak", foldEnrichment: 1.2, pValue: 0.5, fdr: 0.6 }),
];

describe("useEnrichmentTableState", () => {
  it("sorts by p-value ascending with the unknown one last", () => {
    const { result } = renderHook(() => useEnrichmentTableState(TERMS));
    expect(result.current.sorted.map((t) => t.termId)).toEqual([
      "finite",
      "unbounded",
      "weak",
    ]);
  });

  it("puts a term with no FDR last when sorting by FDR ascending", () => {
    const { result } = renderHook(() => useEnrichmentTableState(TERMS));
    act(() => result.current.toggleSort("fdr"));
    expect(result.current.sorted.map((t) => t.termId)).toEqual([
      "finite",
      "weak",
      "unbounded",
    ]);
  });

  it("puts an unbounded fold enrichment first when sorting by fold", () => {
    const { result } = renderHook(() => useEnrichmentTableState(TERMS));
    act(() => result.current.toggleSort("foldEnrichment"));
    expect(result.current.sortDir).toBe("desc");
    expect(result.current.sorted.map((t) => t.termId)).toEqual([
      "unbounded",
      "finite",
      "weak",
    ]);
  });

  it("moves an unbounded fold enrichment last when the direction flips", () => {
    const { result } = renderHook(() => useEnrichmentTableState(TERMS));
    act(() => result.current.toggleSort("foldEnrichment"));
    act(() => result.current.toggleSort("foldEnrichment"));
    expect(result.current.sortDir).toBe("asc");
    expect(result.current.sorted.map((t) => t.termId)).toEqual([
      "weak",
      "finite",
      "unbounded",
    ]);
  });

  it("orders fold enrichment numerically when one term is unbounded", () => {
    const { result } = renderHook(() =>
      useEnrichmentTableState([
        term({ termId: "smaller", foldEnrichment: 9.5 }),
        term({ termId: "unbounded", foldEnrichment: null }),
        term({ termId: "larger", foldEnrichment: 12 }),
      ]),
    );
    act(() => result.current.toggleSort("foldEnrichment"));
    expect(result.current.sorted.map((t) => t.termId)).toEqual([
      "unbounded",
      "larger",
      "smaller",
    ]);
  });

  it("sorts by term name alphabetically", () => {
    const { result } = renderHook(() =>
      useEnrichmentTableState([
        term({ termId: "b", termName: "beta" }),
        term({ termId: "a", termName: "alpha" }),
      ]),
    );
    act(() => result.current.toggleSort("termName"));
    expect(result.current.sorted.map((t) => t.termId)).toEqual(["a", "b"]);
  });
});
