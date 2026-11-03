/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { GeneEvidence } from "@pathfinder/shared/generated/types/GeneEvidence";

import { geneEvidenceOf } from "./__fixtures__/sampleConfirmations";
import { sampleDetail } from "./__fixtures__/sampleRun";
import { GeneEvidenceSection } from "./GeneEvidenceSection";

function pigaRecord(): GeneEvidence {
  const [record] = geneEvidenceOf(sampleDetail("pseudogene_call")).evidence;
  if (record === undefined) throw new Error("the sample stores the PIGA record");
  return record;
}

describe("GeneEvidenceSection", () => {
  it("reads the recorded PIGA record as the site serves it", () => {
    render(
      <GeneEvidenceSection
        evidence={geneEvidenceOf(sampleDetail("pseudogene_call"))}
      />,
    );
    expect(
      screen.getByRole("region", { name: "What the site's gene records hold" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 3,
        name: "What the site's gene records hold",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("PF3D7_1032400: 2 PubMed articles, 0 comments, 0 notes"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("PF3D7_1032400.1: 461 residues, 7 exons"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "AlphaFold Q8IJ83 (SWISSPROT direct link): residues 1 to 461 of 461",
      ),
    ).toBeInTheDocument();
    const pdb = screen.getByRole("table", {
      name: "PDB similarities of PF3D7_1032400: 4",
    });
    expect(within(pdb).getAllByRole("row")[1]).toHaveTextContent(
      "3mboGlycosyltransferase, group 1 familyBacillus anthracis24%53%1.43e-12",
    );
    expect(screen.getByText("No mass-spec peptide served")).toBeInTheDocument();
    expect(
      screen.getByText(
        "PlasmoMAP a network of functional interactions between P. falciparum proteins: PF10_0316",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("protein id: CZT98581.1")).toBeInTheDocument();
    expect(screen.getByText("No sequence edit served")).toBeInTheDocument();
  });

  it("shows the phenotype rows the record holds under any table", () => {
    render(
      <GeneEvidenceSection
        evidence={geneEvidenceOf(sampleDetail("pseudogene_call"))}
      />,
    );
    expect(
      screen.getByText(
        /^EdaPhenotypeGraphsDataTable: value: 0\.7980, variable: Mutagenesis Index Score, dataset id: PlasmoDB_pfal3D7_pB_mutagenesis_MIS_MFS_Phenotype_RSRC; value: 3209\.0000/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("No phenotype screen holds a row for this gene")).toBe(
      null,
    );
  });

  it("says no phenotype screen holds a row only when none does", () => {
    const record = pigaRecord();
    render(
      <GeneEvidenceSection
        evidence={{
          genes: [record.gene],
          evidence: [{ ...record, unprefixedTables: [] }],
        }}
      />,
    );
    expect(
      screen.getByText("No phenotype screen holds a row for this gene"),
    ).toBeInTheDocument();
  });

  it("counts peptides and spectra, and names the tables the site does not serve", () => {
    const record = pigaRecord();
    render(
      <GeneEvidenceSection
        evidence={{
          genes: [record.gene],
          evidence: [
            {
              ...record,
              peptides: [
                {
                  transcript: "PF3D7_1032400.1",
                  sequence: "TKANSISNFSMTYDR",
                  start: 8,
                  end: 22,
                  experiments: [],
                  spectra: 1,
                },
                {
                  transcript: "PF3D7_1032400.1",
                  sequence: "ANSISNFSMTYDR",
                  start: 10,
                  end: 22,
                  experiments: [],
                  spectra: 59,
                },
              ],
              seqedits: [
                {
                  kind: "substitution",
                  lengthDiff: "0",
                  location: "120",
                  diff: null,
                },
              ],
              pdbHits: [],
              unserved: ["Notes", "UserComments"],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("2 mass-spec peptides, 60 spectra")).toBeInTheDocument();
    expect(
      screen.getByText("kind: substitution, length change: 0, location: 120"),
    ).toBeInTheDocument();
    expect(screen.getByText("No PDB similarity served")).toBeInTheDocument();
    expect(
      screen.getByText("Tables the site does not serve: Notes and UserComments"),
    ).toBeInTheDocument();
  });

  it("renders a served name as text and reads an ordinary E-value plainly", () => {
    const record = pigaRecord();
    const hit = record.pdbHits[0];
    if (hit === undefined) throw new Error("the PIGA record holds PDB hits");
    const { container } = render(
      <GeneEvidenceSection
        evidence={{
          genes: [record.gene],
          evidence: [{ ...record, pdbHits: [{ ...hit, evalue: 0.25 }] }],
        }}
      />,
    );
    expect(container.querySelector("i")).toBe(null);
    expect(screen.getByRole("cell", { name: "0.25" })).toBeInTheDocument();
  });
});
