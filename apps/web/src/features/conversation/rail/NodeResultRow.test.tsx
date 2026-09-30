/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import { BuildDetail } from "./LedgerPanelDetail";

function built(): InvestigationLedger["build"] {
  return {
    pushedCount: 1,
    failedCount: 0,
    skippedCount: 0,
    zeroResultSteps: [],
    needsRecovery: false,
    recoveryKind: "none",
    succeeded: true,
    wdkStrategyId: null,
    nodeResults: [{ nodeId: "n1", searchName: "GenesByText", status: "zero" }],
  };
}

describe("BuildDetail rows", () => {
  it("shows no count: the live counts are the facts part's", () => {
    render(<BuildDetail build={built()} />);

    expect(screen.queryByText(/genes/)).not.toBeInTheDocument();
  });

  it("keeps the search name and the build status", () => {
    render(<BuildDetail build={built()} />);

    expect([
      screen.getByText("GenesByText").textContent,
      screen.getByText("zero").textContent,
    ]).toEqual(["GenesByText", "zero"]);
  });
});
