/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import type { Criterion } from "@pathfinder/shared/generated/types/Criterion";
import { FrameDetail } from "./LedgerPanelDetail";

function frameWith(crit: Partial<Criterion>): InvestigationLedger["frame"] {
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
      goal: "g",
      interpretedGoal: "g",
      recordType: "transcript",
      organismScope: null,
      title: "t",
      criteria: [
        {
          id: "c1",
          text: "trophozoite expression",
          searchName: "GenesByMicroarray",
          role: "filter",
          resolvedParams: {
            min_expression_percentile: { type: "number", value: 90 },
            any_or_all: { type: "string", value: "any" },
          },
          openParams: [],
          confidence: 1,
          ...crit,
        },
      ],
      dropped: [],
      openSlots: [],
    },
  };
}

describe("a value the search chose, not the request", () => {
  it("marks an assumed parameter", () => {
    // A default is a safe choice and a silent one. The researcher has to be
    // able to see which values they never asked for.
    render(<FrameDetail frame={frameWith({ defaultedParams: ["any_or_all"] })} />);

    expect(screen.getByTitle(/assumed/i)).toBeInTheDocument();
  });

  it("leaves a stated parameter unmarked", () => {
    render(<FrameDetail frame={frameWith({ defaultedParams: ["any_or_all"] })} />);

    expect(screen.queryAllByTitle(/assumed/i)).toHaveLength(1);
  });

  it("marks nothing when the request stated everything", () => {
    render(<FrameDetail frame={frameWith({ defaultedParams: [] })} />);

    expect(screen.queryByTitle(/assumed/i)).not.toBeInTheDocument();
  });

  it("still shows the value itself", () => {
    render(<FrameDetail frame={frameWith({ defaultedParams: ["any_or_all"] })} />);

    expect(screen.getByText(/any_or_all/)).toBeInTheDocument();
  });
});
