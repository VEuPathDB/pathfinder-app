/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
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
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

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

function inThread(ui: ReactElement<{ data: object }>) {
  const messages = threadOf([threadPart("data-enrichment-results", ui.props.data)]);
  return render(
    <ChatHelpersProvider value={chatHelpersFor(messages)}>{ui}</ChatHelpersProvider>,
  );
}

describe("DataEnrichmentResults", () => {
  it("captions the figure with the term count and the genes analyzed", () => {
    inThread(<DataEnrichmentResults data={CHUNK} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Table 1. 2 terms, 1,342 genes analyzed",
    );
  });

  it("titles the figure Enrichment and keeps the gene set name in the body", () => {
    inThread(<DataEnrichmentResults data={CHUNK} />);
    const title = screen.getByText("Enrichment");
    expect(title.parentElement?.tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("data-enrichment-results")).toHaveTextContent(
      "Erythrocytic kinases",
    );
  });

  it("keeps the CSV download the backend attached", () => {
    inThread(<DataEnrichmentResults data={CHUNK} />);
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
      "href",
      "https://plasmodb.org/enrichment.csv",
    );
  });

  it("draws no divider, no card and no outer margin", () => {
    inThread(<DataEnrichmentResults data={CHUNK} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-enrichment-results").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});
