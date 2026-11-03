/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  pseudogeneConfirmation,
  strainConfirmation,
} from "./__fixtures__/sampleConfirmations";
import { confirmationTracks } from "./proteinTracks";
import { ProteinFigure } from "./ProteinFigure";

describe("ProteinFigure", () => {
  it("draws the strain pair and states it in words", () => {
    const { container } = render(
      <ProteinFigure
        title="Protein lengths of the two models"
        tracks={confirmationTracks(strainConfirmation())}
      />,
    );
    expect(
      screen.getByRole("img", { name: /Protein lengths of the two models/ }),
    ).toBeInTheDocument();
    const mark = container.querySelector('[data-kind="missing"]');
    expect(mark).toHaveAttribute("x", "70.4");
    expect(mark).toHaveAttribute("width", "105.6");
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Reference model PCYB_074210: 341 residues; missing from the other model: residues 41 to 100",
      "Strain model PcyM_0736700: 280 residues",
    ]);
    expect(screen.getByText("missing from the other model")).toBeInTheDocument();
  });

  it("states a premature stop by its residue and names only the marks it draws", () => {
    const stored = pseudogeneConfirmation();
    render(
      <ProteinFigure
        title="The two coding sequences"
        tracks={confirmationTracks({
          ...stored,
          result: { ...stored.result, prematureStops: [163] },
        })}
      />,
    );
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent(
      "codons: 462 codons; stop codon: residue 163",
    );
    expect(screen.getByText("stop codon")).toBeInTheDocument();
    expect(screen.queryByText("missing from the other model")).toBe(null);
  });
});
