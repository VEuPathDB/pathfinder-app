/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";

import { sampleDetail } from "./__fixtures__/sampleRun";
import type { RelativesPoints } from "./relativesPoints";
import { relativesOutcome, stripX } from "./relativesPoints";
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

function plotted(detail: FindingDetail): RelativesPoints {
  const outcome = relativesOutcome(detail);
  if (outcome.kind !== "plotted") throw new Error("the finding stores lengths to plot");
  return outcome.points;
}

function strainDetailWith(
  members: { organism: string; length: number }[],
  missing: "PARALOGS" | "FEWER_THAN_TWO" | "RESIDUAL_GROUP" | null,
): FindingDetail {
  const detail = sampleDetail("strain_model");
  return {
    ...detail,
    evidence: detail.evidence.map((evidence) => {
      const { payload } = evidence;
      if (
        payload?.kind !== "confirmation" ||
        payload.confirmation.check !== "strain_model"
      ) {
        return evidence;
      }
      const { confirmation } = payload;
      const { result } = confirmation;
      return {
        ...evidence,
        payload: {
          ...payload,
          confirmation: {
            ...confirmation,
            result: {
              ...result,
              relatives: { ...result.relatives, members, missing },
            },
          },
        },
      };
    }),
  };
}

describe("relativesOutcome", () => {
  it("plots the relatives a length finding stored, with the model, the reference and the median", () => {
    const points = plotted(
      lengthDetailWith({ "Relative C": 300, "Relative B": 296, "Relative A": 319 }),
    );
    expect(points.relatives.map((dot) => [dot.organism, dot.length])).toEqual([
      ["Relative A", 319],
      ["Relative B", 296],
      ["Relative C", 300],
    ]);
    expect([points.model, points.reference, points.median]).toEqual([110, 319, 300]);
    render(<RelativesPlot outcome={{ kind: "plotted", points }} />);
    expect(
      screen.getByRole("img", { name: /median 300 residues/ }),
    ).toHaveAccessibleName(
      "Protein lengths: this model 110 residues, reference 319 residues, median 300 residues, Relative A 319 residues, Relative B 296 residues, Relative C 300 residues",
    );
  });

  it("states that a length finding looked and found too few relatives", () => {
    const outcome = relativesOutcome(lengthDetailWith({}));
    expect(outcome).toEqual({
      kind: "looked",
      reason: "Fewer than two independent related genomes hold the gene.",
    });
    render(<RelativesPlot outcome={outcome} />);
    expect(
      screen.getByText("Fewer than two independent related genomes hold the gene."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/not stored/)).toBe(null);
  });

  it("states the stored reason a strain finding has no relatives", () => {
    expect(
      [
        strainDetailWith([], "PARALOGS"),
        strainDetailWith([], "FEWER_THAN_TWO"),
        strainDetailWith([], "RESIDUAL_GROUP"),
        strainDetailWith([], null),
      ].map(relativesOutcome),
    ).toEqual([
      { kind: "looked", reason: "The related genomes do not hold one copy each." },
      {
        kind: "looked",
        reason: "Fewer than two independent related genomes hold the gene.",
      },
      { kind: "looked", reason: "The ortholog group is a residual group." },
      { kind: "looked", reason: "The check found no related genome's length." },
    ]);
  });

  it("reads a strain finding's relatives from its stored check", () => {
    expect(plotted(sampleDetail("strain_model"))).toEqual({
      relatives: [
        { organism: "Plasmodium relative0 X", length: 335 },
        { organism: "Plasmodium relative1 X", length: 345 },
      ],
      model: 280,
      reference: 341,
      median: 340,
    });
  });

  it("shows nothing for a finding with no relatives row", () => {
    const organelle = relativesOutcome(sampleDetail("organelle_join"));
    expect(organelle).toEqual({ kind: "no_row" });
    expect(relativesOutcome(sampleDetail("gene_length"))).toEqual({ kind: "no_row" });
    const { container } = render(<RelativesPlot outcome={organelle} />);
    expect(container).toBeEmptyDOMElement();
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
    const points = plotted(sampleDetail("strain_model"));
    const { container } = render(
      <RelativesPlot outcome={{ kind: "plotted", points }} />,
    );
    expect(container.querySelectorAll('[data-part="relative"]')).toHaveLength(2);
    expect(container.querySelector('[data-part="model"]')).toHaveAttribute(
      "points",
      "0.0,29 5.0,34 0.0,39 -5.0,34",
    );
    expect(container.querySelector('[data-part="reference"]')).toHaveAttribute(
      "x",
      "559.1",
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

  it("keeps seven tied relatives apart and inside the drawing", () => {
    const relatives = Array.from({ length: 7 }, (_, index) => ({
      organism: `Relative ${String(index)}`,
      length: 300,
    }));
    const { container } = render(
      <RelativesPlot
        outcome={{
          kind: "plotted",
          points: { relatives, model: 110, reference: 319, median: 300 },
        }}
      />,
    );
    const heights = [...container.querySelectorAll('[data-part="relative"]')].map(
      (dot) => Number(dot.getAttribute("cy")),
    );
    expect(new Set(heights).size).toBe(7);
    const box = container.querySelector("svg")?.getAttribute("viewBox")?.split(" ");
    const bottom = Number(box?.[1]) + Number(box?.[3]);
    expect(Math.min(...heights) - 4).toBeGreaterThanOrEqual(Number(box?.[1]));
    expect(Math.max(...heights) + 4).toBeLessThanOrEqual(bottom);
  });

  it("names in its legend only what it draws", () => {
    render(
      <RelativesPlot
        outcome={{
          kind: "plotted",
          points: {
            relatives: [{ organism: "Relative A", length: 300 }],
            model: 110,
            reference: null,
            median: null,
          },
        }}
      />,
    );
    expect(screen.getByText("This model")).toBeInTheDocument();
    expect(screen.queryByText("Reference")).toBe(null);
    expect(screen.queryByText("Median")).toBe(null);
  });
});
