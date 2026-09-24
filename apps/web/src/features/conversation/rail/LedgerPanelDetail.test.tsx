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
  it("names the workflow a waiting criterion waits for, not an unbound search", () => {
    render(
      <FrameDetail
        frame={frameWith({}, { searchName: "", needsAnalysisOn: "DS_e973eadd57" })}
      />,
    );
    expect(screen.getByText("analysis workflow on DS_e973eadd57")).toBeInTheDocument();
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
