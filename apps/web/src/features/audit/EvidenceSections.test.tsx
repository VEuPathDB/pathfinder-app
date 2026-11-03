/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EvidenceViewKindEnumKey } from "@pathfinder/shared/generated/types/EvidenceView";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import { SAMPLE_WORDS, sampleDetail } from "./__fixtures__/sampleRun";
import { ConfirmationSection } from "./ConfirmationSection";
import { EvidenceNote } from "./EvidenceNote";
import { FactList } from "./FactList";
import { RelativesSection } from "./RelativesSection";

const FACTS = [
  { label: "This model", value: "110 residues" },
  { label: "Median of independent related genomes", value: "300 residues" },
];

function factsOf(detail: FindingDetail, kind: EvidenceViewKindEnumKey) {
  const group = detail.facts.find((facts) => facts.kind === kind);
  if (group === undefined) throw new Error(`no ${kind} facts`);
  return group.facts;
}

function evidenceOf(detail: FindingDetail, kind: EvidenceViewKindEnumKey) {
  const found = detail.evidence.find((evidence) => evidence.kind === kind);
  if (found === undefined) throw new Error(`no ${kind} evidence`);
  return found;
}

describe("the evidence sections", () => {
  it("states the verdict and the facts the API stated for a stored confirmation", () => {
    const detail = sampleDetail("strain_model");
    render(
      <ConfirmationSection
        finding={detail.finding}
        evidence={evidenceOf(detail, "confirmation")}
        facts={factsOf(detail, "confirmation")}
        words={SAMPLE_WORDS}
      />,
    );
    expect(
      screen.getByRole("region", { name: "What the genome's DNA shows" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Related genomes match the reference, so the strain model is too short",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reference residues the strain model lacks").nextElementSibling,
    ).toHaveTextContent("41 to 100");
  });

  it("names evidence the run could not read and why", () => {
    const unanswered = evidenceOf(sampleDetail("strain_model"), "gene_evidence");
    render(<EvidenceNote evidence={unanswered} words={SAMPLE_WORDS} />);
    expect(screen.getByText("The site did not answer")).toBeInTheDocument();
    cleanup();
    render(
      <EvidenceNote
        evidence={{
          ...unanswered,
          status: "failed",
          message: "the gene record of PcyM_0736700 is unreadable",
        }}
        words={SAMPLE_WORDS}
      />,
    );
    expect(
      screen.getByText(
        "Could not be read: the gene record of PcyM_0736700 is unreadable",
      ),
    ).toBeInTheDocument();
  });

  it("states a note in place of the facts of evidence not stored", () => {
    const detail = sampleDetail("strain_model");
    render(
      <RelativesSection
        evidence={{ ...evidenceOf(detail, "gene_evidence"), kind: "relatives" }}
        facts={FACTS}
        words={SAMPLE_WORDS}
      />,
    );
    expect(screen.getByText("The site did not answer")).toBeInTheDocument();
    expect(screen.queryByText("This model")).toBe(null);
  });

  it("renders the facts it is given, in order, and the relatives under their heading", () => {
    const stored = evidenceOf(sampleDetail("strain_model"), "confirmation");
    render(<FactList facts={FACTS} />);
    expect(
      [...document.querySelectorAll("dt")].map((term) => [
        term.textContent,
        term.nextElementSibling?.textContent,
      ]),
    ).toEqual([
      ["This model", "110 residues"],
      ["Median of independent related genomes", "300 residues"],
    ]);
    cleanup();
    render(
      <RelativesSection
        evidence={{ ...stored, kind: "relatives" }}
        facts={FACTS}
        words={SAMPLE_WORDS}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Lengths in related genomes" }),
    ).toHaveTextContent("110 residues");
  });

  it("shows the facts only when a confirmation holds no verdict sentence", () => {
    const detail = sampleDetail("strain_model");
    render(
      <ConfirmationSection
        finding={{ ...detail.finding, verdictText: null }}
        evidence={evidenceOf(detail, "confirmation")}
        facts={FACTS}
        words={SAMPLE_WORDS}
      />,
    );
    expect(screen.getByRole("region")).toHaveTextContent(
      "What the genome's DNA showsThis model110 residues",
    );
  });
});
