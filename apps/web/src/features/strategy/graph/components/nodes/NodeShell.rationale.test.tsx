// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";
import { NodeShell, type NodeKind } from "./NodeShell";

const SNAPSHOT: StepSnapshot = {
  step: null,
  lifecycleState: "idle",
  estimatedSize: 212,
  validationErrors: null,
  lastError: null,
  isBusy: false,
  isInvalid: false,
  isFailed: false,
  isDraft: false,
  wdkPushError: null,
};

const CHOSEN: Step = {
  id: "s1",
  kind: "search",
  displayName: "Exported Protein",
  searchName: "GenesByExportPrediction",
  recordType: "transcript",
  parameters: {},
  isFiltered: false,
  criterionText: "genes with a predicted GPI anchor",
  rationale: {
    kind: "search",
    searchName: "GenesByExportPrediction",
    basis: "nearest",
    term: "GPI anchor",
    reason: "no search states a GPI anchor; Exported Protein scored nearest",
    similarity: 0.44,
    compared: [
      { name: "GenesByText", displayName: "Gene Text Search", similarity: 0.41 },
    ],
    toolCallId: "call_gpi",
    short: "nearest to GPI anchor",
  },
};

function renderNode(step: Step, kind: NodeKind = "search") {
  return render(
    <NodeShell
      kind={kind}
      step={step}
      selected={false}
      isUnsaved={false}
      width={168}
      height={96}
      snapshot={SNAPSHOT}
    />,
  );
}

describe("NodeShell rationale", () => {
  afterEach(() => cleanup());

  it("draws why the step runs its search, with the reason on hover", () => {
    renderNode(CHOSEN);

    const line = screen.getByTestId("node-rationale");
    expect(line).toHaveTextContent("why: nearest to GPI anchor");
    expect(line).toHaveAttribute(
      "title",
      "no search states a GPI anchor; Exported Protein scored nearest " +
        "(over Gene Text Search 0.41)",
    );
  });

  it("draws no line for a step that records no reason", () => {
    renderNode({ ...CHOSEN, rationale: null });

    expect(screen.getByTestId("node-subtitle")).toHaveTextContent(
      "genes with a predicted GPI anchor",
    );
    expect(screen.queryByTestId("node-rationale")).toBeNull();
  });

  it("draws no line for a combine", () => {
    renderNode({ ...CHOSEN, kind: "combine", operator: "UNION" }, "combine");

    expect(screen.getByTestId("node-title")).toHaveTextContent("Exported Protein");
    expect(screen.queryByTestId("node-rationale")).toBeNull();
  });
});
