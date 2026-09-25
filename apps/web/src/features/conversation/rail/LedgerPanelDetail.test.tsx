/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import type { Criterion } from "@pathfinder/shared/generated/types/Criterion";

import { FrameDetail } from "./LedgerPanelDetail";

function frameWith(
  resolvedParams: NonNullable<Criterion["resolvedParams"]>,
  criterion: Partial<Criterion> = {},
): InvestigationLedger["frame"] {
  return {
    present: true,
    diff: null,
    criteriaCount: 1,
    boundCount: 1,
    openSlotCount: 0,
    droppedCount: 0,
    readyToBuild: true,
    needsUser: false,
    contrasts: [],
    structureRender: null,
    spec: {
      criteria: [
        {
          id: "c1",
          text: "kinases",
          searchName: "GenesByMolecularFunction",
          role: "seed",
          resolvedParams,
          ...criterion,
        },
      ],
      dropped: [],
      openSlots: [],
    },
  };
}

describe("FrameDetail resolved parameters", () => {
  it("shows a text value as the text, not as its wire wrapper", () => {
    render(
      <FrameDetail
        frame={frameWith({ stage: { type: "string", value: "gametocyte" } })}
      />,
    );
    expect(screen.getByText("gametocyte")).toBeInTheDocument();
    expect(screen.queryByText(/"type":"string"/)).toBeNull();
  });

  it("shows a number range as a readable range", () => {
    render(
      <FrameDetail
        frame={frameWith({ fold: { type: "number-range", min: 2, max: 8 } })}
      />,
    );
    expect(screen.getByText("2 to 8")).toBeInTheDocument();
  });
});

describe("FrameDetail analysis criteria", () => {
  it("says a waiting search waits for a study, without the study's id", () => {
    render(
      <FrameDetail
        frame={frameWith({}, { searchName: "", needsAnalysisOn: "DS_e973eadd57" })}
      />,
    );
    expect(screen.getByText("waits for a study analysis")).toBeInTheDocument();
    expect(screen.queryByText(/DS_e973eadd57/)).toBeNull();
    expect(screen.queryByText("(unbound)")).toBeNull();
  });

  it("states a bound analysis by the genes it selects", () => {
    const words = "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)";
    render(
      <FrameDetail
        frame={frameWith(
          {},
          {
            text: "24 h over 18 h",
            searchName: "GenesByEdaVizWithCompute",
            analysis: { datasetId: "DS_e973eadd57", words },
          },
        )}
      />,
    );
    expect(screen.getByText(words)).toBeInTheDocument();
  });
});

describe("FrameDetail search reasons", () => {
  it("says why a framed criterion runs its search before anything is built", () => {
    render(
      <FrameDetail
        frame={frameWith(
          {},
          {
            rationale: {
              kind: "search",
              searchName: "GenesByMolecularFunction",
              basis: "parameter",
              term: "GO Term",
              reason: "sets GO Term to protein kinase activity",
              toolCallId: "call_1",
              short: "sets GO Term",
            },
          },
        )}
      />,
    );

    expect(screen.getByTestId("criterion-why").textContent).toBe("why: sets GO Term");
  });

  it("says a measured criterion was chosen by the controls it separated", () => {
    render(
      <FrameDetail
        frame={frameWith(
          {},
          {
            rationale: {
              kind: "controls",
              taskId: "0c6100d2-0000-4000-8000-00000000a16a",
              searchName: "GenesByGoTerm",
              source: "enrichment",
              basis: "GO:0044217 other organism part",
              informs: "recovering",
              recovered: 42,
              positives: 80,
              admitted: 0,
              negatives: 40,
              resultSize: 637,
              term: "42 of 80 positives",
              short: "recovers 42 of 80 positives, admits 0 of 40 negatives",
            },
          },
        )}
      />,
    );

    const why = screen.getByTestId("criterion-why");
    expect([why.textContent, why.getAttribute("title")]).toEqual([
      "why: recovers 42 of 80 positives, admits 0 of 40 negatives",
      "GO:0044217 other organism part",
    ]);
  });

  it("says nothing for a criterion that records no reason", () => {
    render(<FrameDetail frame={frameWith({})} />);

    expect([
      screen.getByText("kinases").tagName,
      screen.queryByTestId("criterion-why"),
    ]).toEqual(["P", null]);
  });
});
