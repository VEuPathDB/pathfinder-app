/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { GeneEvidence } from "@pathfinder/shared/generated/types/GeneEvidence";
import type { GeneEvidencePayload } from "@pathfinder/shared/generated/types/GeneEvidencePayload";

import { geneEvidenceOf } from "./__fixtures__/sampleConfirmations";
import { SAMPLE_WORDS, sampleDetail } from "./__fixtures__/sampleRun";
import { GeneEvidenceSection } from "./GeneEvidenceSection";

function pigaRecord(): GeneEvidence {
  const [record] = geneEvidenceOf(sampleDetail("pseudogene_call")).evidence;
  if (record === undefined) throw new Error("the sample stores the PIGA record");
  return record;
}

function StoredSection({ evidence }: { evidence: GeneEvidencePayload }) {
  return (
    <GeneEvidenceSection
      evidence={{
        kind: "gene_evidence",
        status: "stored",
        payload: { ...evidence, kind: "gene_evidence" },
        requests: 0,
        attempts: 1,
        stopped: 0,
        message: null,
      }}
      facts={[]}
      words={SAMPLE_WORDS}
    />
  );
}

describe("GeneEvidenceSection", () => {
  it("reads the recorded PIGA record as the site serves it", () => {
    render(
      <StoredSection evidence={geneEvidenceOf(sampleDetail("pseudogene_call"))} />,
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
      <StoredSection evidence={geneEvidenceOf(sampleDetail("pseudogene_call"))} />,
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
      <StoredSection
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
      <StoredSection
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
      screen.getByRole("heading", {
        level: 4,
        name: "PF3D7_1032400: 2 PubMed articles, comments not served, notes not served",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("kind: substitution, length change: 0, location: 120"),
    ).toBeInTheDocument();
    expect(screen.getByText("No PDB similarity served")).toBeInTheDocument();
    expect(
      screen.getByText("Tables the site does not serve: Notes and UserComments"),
    ).toBeInTheDocument();
  });

  it("never reads a table the site did not serve as an empty one", () => {
    const record = pigaRecord();
    render(
      <StoredSection
        evidence={{
          genes: [record.gene],
          evidence: [
            {
              ...record,
              pubmed: 0,
              comments: 0,
              notes: 0,
              pdbHits: [],
              peptides: [],
              alphafold: [],
              seqedits: [],
              linkouts: [],
              transcripts: [],
              unprefixedTables: [],
              unserved: [
                "AlphaFoldLinkouts",
                "GeneLinkouts",
                "GeneTranscripts",
                "MassSpecDownload",
                "Notes",
                "PdbSimilarities",
                "PubMed",
                "Seqedits",
                "UserComments",
              ],
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByRole("heading", {
        level: 4,
        name: "PF3D7_1032400: PubMed articles not served, comments not served, notes not served",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("PDB similarities not served")).toBeInTheDocument();
    expect(screen.getByText("Mass-spec peptides not served")).toBeInTheDocument();
    expect(screen.getByText("Sequence edits not served")).toBeInTheDocument();
    expect(screen.queryByText(/^No /)).toBe(
      screen.getByText("No phenotype screen holds a row for this gene"),
    );
  });

  it("states no phenotype negative when an asked screen was not served", () => {
    const record = pigaRecord();
    render(
      <StoredSection
        evidence={{
          genes: [record.gene],
          evidence: [
            {
              ...record,
              unprefixedTables: [],
              unserved: ["pfal3D7_phenotype_pB_mutagenesis_MIS_MFS_RSRC"],
            },
          ],
        }}
      />,
    );
    expect(screen.queryByText("No phenotype screen holds a row for this gene")).toBe(
      null,
    );
    expect(
      screen.getByText(
        "No screen the site served holds a row for this gene, and not every screen was served",
      ),
    ).toBeInTheDocument();
  });

  it("renders a served name as text and reads an ordinary E-value plainly", () => {
    const record = pigaRecord();
    const hit = record.pdbHits[0];
    if (hit === undefined) throw new Error("the PIGA record holds PDB hits");
    const { container } = render(
      <StoredSection
        evidence={{
          genes: [record.gene],
          evidence: [{ ...record, pdbHits: [{ ...hit, evalue: 0.25 }] }],
        }}
      />,
    );
    expect(container.querySelector("i")).toBe(null);
    expect(screen.getByRole("cell", { name: "0.25" })).toBeInTheDocument();
  });

  it("reads an unserved table the run asks for as no sign of a missing screen", () => {
    const record = pigaRecord();
    render(
      <StoredSection
        evidence={{
          genes: [record.gene],
          evidence: [
            {
              ...record,
              phenotypes: [],
              unprefixedTables: [],
              unserved: SAMPLE_WORDS.evidenceTables,
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByText("No phenotype screen holds a row for this gene"),
    ).toBeInTheDocument();
  });

  it("draws one transcript bar with its structure", () => {
    const { container } = render(
      <StoredSection evidence={geneEvidenceOf(sampleDetail("pseudogene_call"))} />,
    );
    expect(
      screen.getByRole("img", {
        name: /Protein lengths of the transcripts of PF3D7_1032400/,
      }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll('[data-kind="structure"]')).toHaveLength(1);
  });

  it("states a row that is not stored in its note", () => {
    render(
      <GeneEvidenceSection
        evidence={{
          kind: "gene_evidence",
          status: "unread",
          payload: null,
          requests: 0,
          attempts: 1,
          stopped: 0,
          message: null,
        }}
        facts={[]}
        words={SAMPLE_WORDS}
      />,
    );
    expect(
      screen.getByRole("region", { name: "What the site's gene records hold" }),
    ).toHaveTextContent("Not read before the run's deadline");
    expect(screen.queryByRole("img")).toBe(null);
  });
});
