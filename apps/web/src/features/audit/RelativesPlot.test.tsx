/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import { sampleDetail } from "./__fixtures__/sampleRun";
import { relativesPoints, stripX } from "./relativesPoints";
import { RelativesPlot } from "./RelativesPlot";

function lengthDetailWith(relativeLengths: Record<string, number>): FindingDetail {
  const detail = sampleDetail("gene_length");
  return {
    ...detail,
    evidence: [
      ...detail.evidence,
      {
        kind: "relatives",
        status: "stored",
        payload: {
          kind: "relatives",
          referenceGene: "REF",
          referenceLength: 319,
          modelLength: 110,
          relativesMedian: 300,
          relativeLengths,
          relativesTier: null,
          side: "STRAIN_SHORT",
          referenceOrganism: null,
        },
        requests: 0,
        attempts: 1,
        stopped: 0,
        message: null,
      },
    ],
  };
}

describe("relativesPoints", () => {
  it("plots the relatives a length finding stored, with the model, the reference and the median", () => {
    const points = relativesPoints(
      lengthDetailWith({ "Relative C": 300, "Relative B": 296, "Relative A": 319 }),
    );
    expect(points?.relatives.map((dot) => [dot.organism, dot.length])).toEqual([
      ["Relative A", 319],
      ["Relative B", 296],
      ["Relative C", 300],
    ]);
    expect([points?.model, points?.reference, points?.median]).toEqual([110, 319, 300]);
    if (points === null) throw new Error("the finding stores its relatives");
    render(<RelativesPlot points={points} />);
    expect(
      screen.getByRole("img", { name: /median 300 residues/ }),
    ).toHaveAccessibleName(
      "Protein lengths: this model 110 residues, reference 319 residues, median 300 residues, Relative A 319 residues, Relative B 296 residues, Relative C 300 residues",
    );
  });

  it("says a length finding stored before its relatives' lengths were kept has none to plot", () => {
    expect(relativesPoints(lengthDetailWith({}))).toBe(null);
    render(<RelativesPlot points={null} />);
    expect(screen.getByText("Relatives' lengths not stored")).toBeInTheDocument();
  });

  it("reads a strain finding's relatives from its stored check", () => {
    expect(relativesPoints(sampleDetail("strain_model"))).toEqual({
      relatives: [
        { organism: "Plasmodium relative0 X", length: 335 },
        { organism: "Plasmodium relative1 X", length: 345 },
      ],
      model: 280,
      reference: 341,
      median: 340,
    });
  });

  it("has nothing to plot for a finding that stores no relatives", () => {
    expect(relativesPoints(sampleDetail("organelle_join"))).toBe(null);
    expect(relativesPoints(sampleDetail("gene_length"))).toBe(null);
  });
});

describe("the strip", () => {
  it("places lengths on one axis from the shortest to the longest", () => {
    const lengths = [280, 335, 340, 341, 345];
    expect(stripX(280, lengths, 600)).toBe(0);
    expect(stripX(345, lengths, 600)).toBe(600);
    expect(stripX(341, lengths, 600)).toBeCloseTo((61 / 65) * 600, 6);
  });

  it("draws one dot per relative and marks the model, the reference and the median", () => {
    const points = relativesPoints(sampleDetail("strain_model"));
    if (points === null) throw new Error("the sample strain finding stores relatives");
    const { container } = render(<RelativesPlot points={points} />);
    expect(container.querySelectorAll('[data-part="relative"]')).toHaveLength(2);
    expect(container.querySelector('[data-part="model"]')).toHaveAttribute(
      "data-x",
      "0.0",
    );
    expect(container.querySelector('[data-part="median"]')).toHaveAttribute(
      "x1",
      "553.8",
    );
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "This model: 280 residues",
      "Reference: 341 residues",
      "Median of the related genomes: 340 residues",
      "Plasmodium relative0 X: 335 residues",
      "Plasmodium relative1 X: 345 residues",
    ]);
  });
});
