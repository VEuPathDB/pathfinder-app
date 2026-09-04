/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import { BuildDetail } from "./LedgerPanelDetail";

function buildWith(count: number): InvestigationLedger["build"] {
  return {
    pushedCount: 1,
    failedCount: 0,
    skippedCount: 0,
    zeroResultSteps: [],
    needsRecovery: false,
    recoveryKind: "none",
    succeeded: true,
    wdkStrategyId: null,
    wdkUrl: null,
    nodeResults: [{ nodeId: "n1", searchName: "GenesByText", count, status: "ok" }],
  };
}

describe("BuildDetail counts", () => {
  it("says a count is from the build, not what the strategy holds now", () => {
    // The strategy rail shows the live count. An edit outside the build moves
    // one and not the other, so an unqualified number reads as current fact.
    render(<BuildDetail build={buildWith(3259)} />);

    expect(screen.getByText(/3,259 genes at build/)).toBeInTheDocument();
  });

  it("still shows the number", () => {
    render(<BuildDetail build={buildWith(15)} />);

    expect(screen.getByText(/15/)).toBeInTheDocument();
  });

  it("keeps the search name", () => {
    render(<BuildDetail build={buildWith(1)} />);

    expect(screen.getByText("GenesByText")).toBeInTheDocument();
  });
});
