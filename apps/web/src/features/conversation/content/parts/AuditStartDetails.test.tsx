/**
 * @vitest-environment jsdom
 */
import type { AuditStartCard } from "@strategist/shared/generated/types/AuditStartCard";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { AuditStartDetails } from "./AuditStartDetails";

const CARD: AuditStartCard = {
  toolCallId: "call-1",
  siteId: "exampledb",
  genomes: ["Examplea alpha A", "Examplea alpha B"],
  comparison: ["Examplea alpha C", "Examplea alpha D"],
  referenceGenome: "Examplea alpha R",
  checks: ["gene_length", "intron_support"],
  checkTitles: ["Gene length against orthologs", "Exon structure against RNA-seq"],
  targets: 3,
  leftOut: ["Examplea alpha I"],
  refusedTargets: [],
  wdkRequests: 240,
  storeReads: 12,
  hours: 1.5,
  hoursAtMost: 6,
  modelReviews: 50,
};

function lines(): string[] {
  return screen.getAllByRole("listitem").map((item) => item.textContent);
}

describe("AuditStartDetails", () => {
  it("states each fact of the start card in plain words", () => {
    render(<AuditStartDetails card={CARD} />);
    expect(lines()).toEqual([
      "Genomes: Examplea alpha A, Examplea alpha B",
      "Left out: Examplea alpha I",
      "Compared with 2 genomes",
      "Reference: Examplea alpha R",
      "Checks: Gene length against orthologs, Exon structure against RNA-seq",
      "3 gene targets",
      "About 240 site requests and 12 genome-store reads",
      "About 1.5 hours, at most 6 hours",
      "Up to 50 model reviews",
    ]);
  });

  it("names no internal word", () => {
    render(<AuditStartDetails card={CARD} />);
    expect(document.body.textContent).not.toMatch(/WDK|gene_length|_/);
  });

  it("leaves out what the card does not hold", () => {
    render(
      <AuditStartDetails
        card={{
          ...CARD,
          leftOut: [],
          comparison: [],
          referenceGenome: null,
          targets: 0,
        }}
      />,
    );
    expect(lines()).toEqual([
      "Genomes: Examplea alpha A, Examplea alpha B",
      "Checks: Gene length against orthologs, Exon structure against RNA-seq",
      "About 240 site requests and 12 genome-store reads",
      "About 1.5 hours, at most 6 hours",
      "Up to 50 model reviews",
    ]);
  });

  it("states a short run in minutes", () => {
    render(<AuditStartDetails card={{ ...CARD, hours: 102 / 3600 }} />);
    expect(screen.getByText("About 2 minutes, at most 6 hours")).toBeInTheDocument();
  });

  it("states each refused target with its reason", () => {
    render(
      <AuditStartDetails
        card={{
          ...CARD,
          refusedTargets: [
            {
              target: { check: "intron_support", genes: ["EXB_0001"] },
              title: "Exon structure against RNA-seq, EXB_0001",
              reason:
                "ExampleDB serves no RNA-seq junction track for the genome of EXB_0001",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/^Not checked:/)).toHaveTextContent(
      "Not checked: Exon structure against RNA-seq, EXB_0001, because " +
        "ExampleDB serves no RNA-seq junction track for the genome of EXB_0001",
    );
  });
});
