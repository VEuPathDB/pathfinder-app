// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import { useStrategyStore } from "@/state/strategy/store";
import { SearchNode } from "./SearchNode";
import type { StepNodeProps } from "./types";

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    Handle: ({ id, type }: { id?: string; type: string }) =>
      React.createElement("span", {
        "data-testid": `flow-handle-${type}-${id ?? "default"}`,
      }),
    NodeToolbar: ({ children }: { children?: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "node-toolbar" }, children),
    Position: { Top: "top", Right: "right", Bottom: "bottom", Left: "left" },
  };
});

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    kind: "search",
    displayName: "Genes by taxon",
    searchName: "GenesByTaxon",
    recordType: "gene",
    parameters: { organism: { type: "single-pick-vocabulary", value: "Plasmodium" } },
    estimatedSize: 1234,
    isFiltered: false,
    validation: null,
    ...overrides,
  };
}

function reset() {
  useStrategyStore.setState({
    stepLifecycleById: {},
    undoStack: [],
    redoStack: [],
  });
}

function defaultProps(step: Step): StepNodeProps {
  return {
    step,
    selected: false,
    showOutputHandle: true,
    showPrimaryInputHandle: false,
    showSecondaryInputHandle: false,
  };
}

describe("SearchNode", () => {
  beforeEach(reset);

  it("renders the step name and result count", () => {
    const step = makeStep({ estimatedSize: 1234 });
    render(<SearchNode {...defaultProps(step)} />);
    expect(screen.getByText("Genes by taxon")).toBeTruthy();
    expect(screen.getByText(/1,234/)).toBeTruthy();
  });

  it("shows a shimmer skeleton while count is loading", () => {
    const step = makeStep({ estimatedSize: null });
    useStrategyStore.getState().initStepLifecycle("s1");
    useStrategyStore.getState().dispatchStepEvent("s1", { type: "VALIDATE" });
    const { container } = render(<SearchNode {...defaultProps(step)} />);
    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(1);
  });

  it("shows validation error treatment with left border + corner dot", () => {
    const step = makeStep({ estimatedSize: null });
    useStrategyStore.getState().applyStepValidationErrors({ s1: "Missing organism" });
    const { container } = render(<SearchNode {...defaultProps(step)} />);
    expect(screen.getByTestId("rf-node-s1")).toHaveAttribute(
      "data-validation",
      "error",
    );
    expect(container.querySelectorAll('[data-corner-dot="error"]')).toHaveLength(1);
  });

  it("renders an output handle on the right when allowed", () => {
    const step = makeStep();
    render(<SearchNode {...defaultProps(step)} />);
    expect(screen.getByTestId("flow-handle-source-right")).toBeTruthy();
  });

  it("grows by one line when the step says why it runs its search", () => {
    const plain = render(<SearchNode {...defaultProps(makeStep())} />);
    const plainHeight = screen.getByTestId("rf-node-s1").style.height;
    plain.unmount();
    const reasoned = makeStep({
      rationale: {
        kind: "search",
        searchName: "GenesByTaxon",
        basis: "parameter",
        term: "Organism",
        reason: "sets Organism to Plasmodium",
        toolCallId: "call_1",
        short: "sets Organism",
      },
    });
    render(<SearchNode {...defaultProps(reasoned)} />);

    expect([plainHeight, screen.getByTestId("rf-node-s1").style.height]).toEqual([
      "80px",
      "96px",
    ]);
  });
});
