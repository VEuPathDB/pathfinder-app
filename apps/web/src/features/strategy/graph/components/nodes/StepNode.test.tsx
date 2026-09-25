// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Node, NodeProps } from "@xyflow/react";
import { combineOpEnum, type Step } from "@pathfinder/shared";
import { useStrategyStore } from "@/state/strategy/store";
import { StepNode } from "./StepNode";
import type { StepNodeData } from "./types";

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
    parameters: {},
    estimatedSize: 100,
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

function makeNodeProps(
  step: Step,
  selected: boolean,
  extra: Partial<StepNodeData> = {},
): NodeProps<Node<StepNodeData>> {
  return {
    id: step.id,
    type: "step",
    data: {
      step,
      showOutputHandle: true,
      showPrimaryInputHandle: true,
      showSecondaryInputHandle: true,
      ...extra,
    },
    selected,
    dragging: false,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
  };
}

describe("StepNode dispatcher", () => {
  beforeEach(reset);

  it("dispatches to SearchNode for kind=search and renders the search step's name", () => {
    const step = makeStep({ kind: "search", displayName: "Kinase genes" });
    const { container } = render(<StepNode {...makeNodeProps(step, false)} />);
    expect(container.querySelector('[data-kind="search"]')).not.toBeNull();
    expect(screen.getByText("Kinase genes")).toBeInTheDocument();
  });

  it("dispatches to CombineNode for kind=combine and renders the operator badge", () => {
    const step = makeStep({
      kind: "combine",
      displayName: "Kinases AND drug targets",
      operator: combineOpEnum.INTERSECT,
      primaryInputStepId: "a",
      secondaryInputStepId: "b",
    });
    const { container } = render(<StepNode {...makeNodeProps(step, false)} />);
    expect(container.querySelector('[data-kind="combine"]')).not.toBeNull();
    expect(screen.getByTestId("combine-operator-badge").textContent).toBe("Intersect");
  });

  it("dispatches to TransformNode for kind=transform and renders its name", () => {
    const step = makeStep({
      kind: "transform",
      displayName: "Orthologs in P. berghei",
      primaryInputStepId: "a",
    });
    const { container } = render(<StepNode {...makeNodeProps(step, false)} />);
    expect(container.querySelector('[data-kind="transform"]')).not.toBeNull();
    expect(screen.getByText("Orthologs in P. berghei")).toBeInTheDocument();
  });

  it("renders a selection ring on the shell when selected=true", () => {
    const step = makeStep();
    render(<StepNode {...makeNodeProps(step, true)} />);
    expect(screen.getByTestId(`rf-node-${step.id}`)).toHaveAttribute(
      "data-selected",
      "true",
    );
  });

  it("fires onOpenDetails with the step id when the edit chip is clicked", async () => {
    const step = makeStep({ id: "step-kinases" });
    const onOpenDetails = vi.fn();
    render(<StepNode {...makeNodeProps(step, false, { onOpenDetails })} />);
    await userEvent.click(screen.getByTestId(`rf-edit-${step.id}`));
    expect(onOpenDetails).toHaveBeenCalledWith("step-kinases");
  });

  it("tags the rendered node with data-orphan when isOrphan is true", () => {
    const step = makeStep();
    const { container } = render(
      <StepNode {...makeNodeProps(step, false, { isOrphan: true })} />,
    );
    expect(container.querySelectorAll('[data-orphan="true"]')).toHaveLength(1);
  });

  it("data-orphan is false by default", () => {
    const step = makeStep();
    const { container } = render(<StepNode {...makeNodeProps(step, false)} />);
    expect(container.querySelectorAll('[data-orphan="true"]')).toHaveLength(0);
    expect(container.querySelectorAll('[data-orphan="false"]')).toHaveLength(1);
  });
});
