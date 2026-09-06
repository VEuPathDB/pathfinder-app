/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { EnrichmentTerm } from "@pathfinder/shared";
import { EnrichmentTable } from "./EnrichmentTable";

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

describe("EnrichmentTable", () => {
  afterEach(cleanup);

  it("shows the numbers of a finite term", () => {
    render(<EnrichmentTable terms={[term()]} />);
    const row = screen.getByRole("row", { name: /protein kinase activity/ });
    expect(row).toHaveTextContent("3.48");
    expect(row).toHaveTextContent("1.00e-4");
    expect(row).toHaveTextContent("2.00e-3");
  });

  it("shows an unbounded fold enrichment as Inf and an unknown p as n/a", () => {
    render(<EnrichmentTable terms={[term({ foldEnrichment: null, pValue: null })]} />);
    const row = screen.getByRole("row", { name: /protein kinase activity/ });
    expect(row).toHaveTextContent("Inf");
    expect(row).toHaveTextContent("n/a");
  });

  it("shows an unbounded odds ratio and an unknown bonferroni in the detail row", async () => {
    render(<EnrichmentTable terms={[term({ oddsRatio: null, bonferroni: null })]} />);

    await userEvent.click(screen.getByText("protein kinase activity"));

    expect(screen.getByText(/Odds Ratio:/)).toHaveTextContent("Odds Ratio: Inf");
    expect(screen.getByText(/Bonferroni:/)).toHaveTextContent("Bonferroni: n/a");
  });
});
