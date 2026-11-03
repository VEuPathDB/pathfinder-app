/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { TargetReport } from "./TargetReport";

describe("TargetReport", () => {
  it("counts the researcher's targets per genome apart from every rate", () => {
    render(<TargetReport report={SAMPLE_RUN.targets} words={SAMPLE_WORDS} />);
    expect(
      screen.getByRole("heading", { level: 2, name: "Your gene targets" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "These genes are in no rate: you chose them, so they are not a random sample.",
      ),
    ).toBeInTheDocument();
    const rows = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        [...row.querySelectorAll("th, td")].map((cell) => cell.textContent),
      );
    expect(rows).toEqual([
      [
        "Plasmodium cynomolgi strain B",
        "Strain model against its reference",
        "1",
        "0",
        "0",
        "0",
      ],
      [
        "Plasmodium cynomolgi strain M",
        "Exon structure against RNA-seq",
        "1",
        "1",
        "0",
        "0",
      ],
      [
        "Plasmodium cynomolgi strain M",
        "Strain model against its reference",
        "1",
        "1",
        "0",
        "0",
      ],
      [
        "Plasmodium falciparum NF54",
        "Organelle genes at the circular join",
        "1",
        "1",
        "0",
        "0",
      ],
    ]);
    expect(screen.queryByText(/not placed/)).toBe(null);
  });

  it("names the targets the site did not place", () => {
    render(
      <TargetReport
        report={{ ...SAMPLE_RUN.targets, unplaced: 2 }}
        words={SAMPLE_WORDS}
      />,
    );
    expect(
      screen.getByText(
        "2 targets not placed in a genome: the run holds no genome for their genes.",
      ),
    ).toBeInTheDocument();
  });
});
