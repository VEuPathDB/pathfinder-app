// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";
import { NodeShell } from "./NodeShell";

const WORDS = "genes with a predicted GPI anchor";

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

function exported(criterionText: string | null): Step {
  return {
    id: "s1",
    kind: "search",
    displayName: "Exported Protein",
    searchName: "GenesByExportPrediction",
    recordType: "transcript",
    parameters: {},
    isFiltered: false,
    criterionText,
  };
}

function renderNode(step: Step) {
  return render(
    <NodeShell
      kind="search"
      step={step}
      selected={false}
      width={168}
      height={80}
      snapshot={SNAPSHOT}
    />,
  );
}

describe("NodeShell subtitle", () => {
  afterEach(() => cleanup());

  it("titles the node by what runs and draws the request's words beneath it", () => {
    renderNode(exported(WORDS));

    expect(screen.getByTestId("node-title")).toHaveTextContent("Exported Protein");
    const subtitle = screen.getByTestId("node-subtitle");
    expect(subtitle).toHaveTextContent(WORDS);
    expect(subtitle).toHaveAttribute("title", WORDS);
  });

  it("draws no subtitle for a step that carries no words", () => {
    renderNode(exported(null));

    expect(screen.getByTestId("node-title")).toHaveTextContent("Exported Protein");
    expect(screen.queryByTestId("node-subtitle")).toBeNull();
  });
});
