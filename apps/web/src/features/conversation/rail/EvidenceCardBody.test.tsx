/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { ControlTestEvidence } from "@pathfinder/shared";

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

describe("EvidenceCardBody control tests", () => {
  const tested: ControlTestEvidence = {
    testedLabel: "Genes by Molecular Weight",
    wdkStepId: 440299573,
    positive: {
      returned: ["PF3D7_0102600"],
      notReturned: [],
      controlsCount: 1,
      returnedCount: 1,
      rate: 1,
    },
  };

  function captions(controls: ControlTestEvidence[]): string[] {
    render(<EvidenceCardBody card={{ ...EVIDENCE_CARD, controls }} />);
    return screen
      .getAllByTestId("evidence-controls")
      .map((table) => table.querySelector("p")?.textContent ?? "");
  }

  it("names the saved set a control test ran", () => {
    expect(
      captions([
        { ...tested, controlSet: { id: "cs-1", name: "Signal peptide controls" } },
      ]),
    ).toEqual(["Control test of Signal peptide controls on Genes by Molecular Weight"]);
  });

  it("names only the step when the ids were no saved set", () => {
    expect(captions([{ ...tested, controlSet: null }])).toEqual([
      "Control test on Genes by Molecular Weight",
    ]);
  });

  it("keeps two sets tested on one step as two tables", () => {
    expect(
      captions([
        { ...tested, controlSet: { id: "cs-1", name: "Signal peptide controls" } },
        { ...tested, controlSet: { id: "cs-2", name: "Apicoplast controls" } },
      ]),
    ).toEqual([
      "Control test of Signal peptide controls on Genes by Molecular Weight",
      "Control test of Apicoplast controls on Genes by Molecular Weight",
    ]);
  });
});
