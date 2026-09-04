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
