/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { EVIDENCE_CARD } from "../content/parts/evidenceCardFixture";
import { EvidenceCardBody } from "./EvidenceCardBody";

function citing(references: string[]) {
  render(
    <EvidenceCardBody
      card={{
        ...EVIDENCE_CARD,
        citations: [{ criterionId: "c1", criterionText: "kinases", references }],
      }}
    />,
  );
  return within(screen.getByTestId("evidence-citations"));
}

describe("EvidenceCardBody citations", () => {
  it("links a DOI to doi.org and a PMID to PubMed", () => {
    const cited = citing([
      "10.1038/nature12970",
      "doi:10.1126/science.1",
      "31234567",
      "PMID:7654321",
    ]);

    expect(cited.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "https://doi.org/10.1038/nature12970",
      "https://doi.org/10.1126/science.1",
      "https://pubmed.ncbi.nlm.nih.gov/31234567/",
      "https://pubmed.ncbi.nlm.nih.gov/7654321/",
    ]);
  });

  it("keeps a web address as it is", () => {
    const cited = citing(["https://plasmodb.org/plasmo/app/record/gene/PF3D7_1133400"]);

    expect(cited.getByRole("link").getAttribute("href")).toBe(
      "https://plasmodb.org/plasmo/app/record/gene/PF3D7_1133400",
    );
  });

  it("shows a reference that is no address as text", () => {
    const cited = citing(["javascript:alert(1)", "Smith et al. 2020"]);

    expect(cited.queryAllByRole("link")).toEqual([]);
    expect(cited.getByText("Smith et al. 2020")).toBeInTheDocument();
  });
});

describe("EvidenceCardBody step counts", () => {
  it("heads the site's column with when it was counted", () => {
    render(<EvidenceCardBody card={EVIDENCE_CARD} />);

    const steps = within(screen.getByTestId("evidence-steps"));
    expect(steps.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Step",
      "Recorded at the build",
      "On the site at the check",
    ]);
  });
});
