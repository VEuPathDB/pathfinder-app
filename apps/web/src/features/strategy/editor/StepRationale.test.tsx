// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import { StepRationale } from "./StepRationale";

type Rationale = NonNullable<Step["rationale"]>;

const CHOSEN: Rationale = {
  kind: "search",
  searchName: "GenesByExportPrediction",
  basis: "nearest",
  term: "GPI anchor",
  reason: "no search states a GPI anchor; Exported Protein scored nearest",
  similarity: 0.44,
  compared: [
    { name: "GenesByText", displayName: "Gene Text Search", similarity: 0.41 },
    { name: "GenesWithSignalPeptide", displayName: "Predicted Signal Peptide" },
  ],
  answered: 20,
  query: "GPI anchor attachment signal",
  toolCallId: "call_gpi",
  short: "nearest to GPI anchor",
};

const COMPUTED: Rationale = {
  kind: "analysis",
  datasetId: "DS_e973eadd57",
  method: "DESeq",
  term: "DESeq",
  reason: "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)",
  short: "computed by DESeq",
};

const MEASURED: Rationale = {
  kind: "controls",
  taskId: "0c6100d2-0000-4000-8000-00000000a16a",
  searchName: "GenesByGoTerm",
  source: "literature",
  basis: "exported proteins",
  sources: ["https://doi.org/10.1038/nature03069"],
  informs: "recovering",
  recovered: 42,
  positives: 80,
  admitted: 0,
  negatives: 40,
  resultSize: 637,
  term: "42 of 80 positives",
  short: "recovers 42 of 80 positives, admits 0 of 40 negatives",
};

describe("StepRationale", () => {
  afterEach(() => cleanup());

  it("gives the reason, the query it answered and what it was chosen over", () => {
    render(<StepRationale rationale={CHOSEN} />);

    const block = screen.getByTestId("step-rationale");
    expect(within(block).getByText("Why this search").tagName).toBe("P");
    expect(within(block).getByText(CHOSEN.reason).tagName).toBe("P");
    expect(within(block).getByTestId("step-rationale-query")).toHaveTextContent(
      "catalog query: GPI anchor attachment signal; this search scored 0.44 of 20 answered",
    );
    expect(within(block).getByText("Chosen over").tagName).toBe("P");
    expect(
      within(block)
        .getAllByTestId("step-rationale-compared")
        .map((row) => row.textContent),
    ).toEqual(["Gene Text Search 0.41", "Predicted Signal Peptide not scored"]);
  });

  it("gives an analysis step the compute its document holds", () => {
    render(<StepRationale rationale={COMPUTED} />);

    const block = screen.getByTestId("step-rationale");
    expect(within(block).getByText("Why these genes").tagName).toBe("P");
    expect(within(block).getByText(COMPUTED.reason).tagName).toBe("P");
    expect(within(block).queryByTestId("step-rationale-query")).toBeNull();
  });

  it("gives a measured step the counts its own step returned and the paper", () => {
    render(<StepRationale rationale={MEASURED} />);

    const block = screen.getByTestId("step-rationale");
    expect(within(block).getByText("Chosen by the controls").tagName).toBe("P");
    expect(within(block).getByTestId("step-rationale-counts")).toHaveTextContent(
      "recovers 42 of 80 positives, admits 0 of 40 negatives, 637 genes",
    );
    expect(within(block).getByText("exported proteins").tagName).toBe("SPAN");
    expect(within(block).getByRole("link").getAttribute("href")).toBe(
      "https://doi.org/10.1038/nature03069",
    );
  });
});
