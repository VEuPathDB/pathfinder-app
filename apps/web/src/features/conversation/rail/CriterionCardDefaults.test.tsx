/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BoundValue } from "@pathfinder/shared/generated/types/BoundValue";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import { FrameDetail } from "./LedgerPanelDetail";

function frameWith(
  anyOrAll: BoundValue["source"],
  basis = "",
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
            min_expression_percentile: {
              value: { type: "number", value: 90 },
              source: "stated",
              basis: "90",
            },
            any_or_all: {
              value: { type: "string", value: "any" },
              source: anyOrAll,
              basis,
            },
          },
          openParams: [],
          confidence: 1,
        },
      ],
      dropped: [],
      openSlots: [],
    },
  };
}

describe("a value the request did not state shows who set it", () => {
  it("marks a site default", () => {
    render(<FrameDetail frame={frameWith("default")} />);

    expect(screen.getByTitle(/the site's default/i)).toHaveTextContent("site default");
  });

  it("marks a value the assistant chose, with its reason", () => {
    render(<FrameDetail frame={frameWith("chosen", "any matches the request")} />);

    expect(screen.getByText("chosen")).toHaveAttribute(
      "title",
      "Chosen by the assistant, not a value you stated: any matches the request",
    );
  });

  it("leaves stated and card values unmarked", () => {
    const { rerender } = render(<FrameDetail frame={frameWith("stated")} />);
    expect(screen.queryByTitle(/not a value you stated/i)).not.toBeInTheDocument();

    rerender(<FrameDetail frame={frameWith("card")} />);
    expect(screen.queryByTitle(/not a value you stated/i)).not.toBeInTheDocument();
  });

  it("still shows the value itself", () => {
    render(<FrameDetail frame={frameWith("default")} />);

    expect(screen.getByText(/any_or_all/)).toBeInTheDocument();
  });
});
