/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { EvidenceCard, ExpressionFit } from "@pathfinder/shared";

import { DataEvidenceCard } from "./DataEvidenceCard";
import { EVIDENCE_CARD } from "./evidenceCardFixture";

const STEP = 440299573;
const OTHER = STEP + 1;
const LABEL = "Phyletic pattern, checked on each step's first groups";

function fit(overrides: Partial<ExpressionFit>): ExpressionFit {
  return {
    wdkStepId: STEP,
    expression: "APIC=139T AND APIC=139",
    sampled: 2,
    held: 2,
    failing: [],
    unmatched: [],
    sentence: `2 of 2 sampled groups of step ${STEP} meet its phyletic expression on the site's per-genome counts`,
    ...overrides,
  };
}

function lines(card: EvidenceCard): string[] {
  render(<DataEvidenceCard data={card} />);
  const list = screen.getByRole("list", { name: LABEL });
  return within(list)
    .getAllByTestId("evidence-expression-fit")
    .map((line) => line.textContent);
}

describe("DataEvidenceCard expression fits", () => {
  it("draws the server's sentence for each step, under the step's title", () => {
    const failing = `1 of 2 sampled groups of step ${OTHER} does not meet its phyletic expression on the site's per-genome counts: OG8_0031041`;
    const card: EvidenceCard = {
      ...EVIDENCE_CARD,
      expressionFits: [
        fit({}),
        fit({ wdkStepId: OTHER, held: 1, failing: ["OG8_0031041"], sentence: failing }),
      ],
    };

    expect(lines(card)).toEqual([
      `Genes by Molecular Weight: 2 of 2 sampled groups of step ${STEP} meet its phyletic expression on the site's per-genome counts`,
      failing,
    ]);
  });

  it("starts an untitled step's line with a capital", () => {
    const unmatched =
      "MAMM<=0T matches no group, because the site counts a unit only in a group with a protein of its codes; write MAMM=0T for absence.";
    const card: EvidenceCard = {
      ...EVIDENCE_CARD,
      expressionFits: [
        fit({
          sampled: 0,
          held: 0,
          unmatched: [unmatched],
          sentence: `step ${STEP} holds no group, and its phyletic expression matches none as the site reads it: ${unmatched}`,
        }),
        fit({
          wdkStepId: OTHER,
          sampled: 0,
          held: 0,
          sentence: `step ${OTHER} holds no group`,
        }),
      ],
    };

    expect(lines(card)).toEqual([
      `Genes by Molecular Weight: step ${STEP} holds no group, and its phyletic expression matches none as the site reads it: ${unmatched}`,
      `Step ${OTHER} holds no group`,
    ]);
  });

  it("draws no list for a card without a phyletic step", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.queryByRole("list", { name: LABEL })).toBeNull();
    expect(screen.queryAllByTestId("evidence-expression-fit")).toHaveLength(0);
  });
});
