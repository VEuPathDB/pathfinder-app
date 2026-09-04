/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { EnrichmentResultsChunk } from "@pathfinder/shared";

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { DataEnrichmentResults } from "./DataEnrichmentResults";

const CHUNK: EnrichmentResultsChunk = {
  taskId: "t-1",
  geneSetId: "gs-1",
  geneSetName: "Erythrocytic kinases",
  geneCount: 1342,
  results: [
    { analysisType: "go_function", terms: [], error: null },
    { analysisType: "pathway", terms: [], error: null },
  ],
  downloads: { csv: "https://plasmodb.org/enrichment.csv" },
};

describe("DataEnrichmentResults", () => {
  it("captions the figure with the term count and the genes analyzed", () => {
    render(<DataEnrichmentResults data={CHUNK} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 terms, 1,342 genes analyzed",
    );
  });

  it("titles the figure Enrichment and keeps the gene set name in the body", () => {
    render(<DataEnrichmentResults data={CHUNK} />);
    const title = screen.getByText("Enrichment");
    expect(title.tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("data-enrichment-results")).toHaveTextContent(
      "Erythrocytic kinases",
    );
  });

  it("keeps the CSV download the backend attached", () => {
    render(<DataEnrichmentResults data={CHUNK} />);
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
      "href",
      "https://plasmodb.org/enrichment.csv",
    );
  });

  it("draws no divider, no card and no outer margin", () => {
    render(<DataEnrichmentResults data={CHUNK} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-enrichment-results").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});
