// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { combineOpEnum, type Step } from "@pathfinder/shared";
import { useStrategyStore } from "@/state/strategy/store";
import { CombineNode } from "./CombineNode";
import type { StepNodeProps } from "./types";

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    Handle: ({
      id,
      type,
      className,
    }: {
      id?: string;
      type: string;
      className?: string;
    }) =>
      React.createElement("span", {
        "data-testid": `flow-handle-${type}-${id ?? "default"}`,
        className,
      }),
    NodeToolbar: ({ children }: { children?: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "node-toolbar" }, children),
    Position: { Top: "top", Right: "right", Bottom: "bottom", Left: "left" },
  };
});

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    kind: "combine",
    displayName: "Combined gene set",
    searchName: "__combine__",
    recordType: "gene",
    parameters: {},
    operator: combineOpEnum.INTERSECT,
    primaryInputStepId: "left",
    secondaryInputStepId: "right",
    estimatedSize: 2891,
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
    showPrimaryInputHandle: true,
    showSecondaryInputHandle: true,
  };
}

describe("CombineNode", () => {
  beforeEach(reset);

  it("renders a mini-venn matching the operator", () => {
    const step = makeStep({ operator: combineOpEnum.INTERSECT });
    const { container } = render(<CombineNode {...defaultProps(step)} />);
    const lens = container.querySelector('[data-region="lens"]');
    expect(lens?.getAttribute("data-active")).toBe("true");
    expect(
      container.querySelector('[data-region="left-only"]')?.getAttribute("data-active"),
    ).toBe("false");
  });

  it("re-renders the venn fill when the operator changes", () => {
    const step = makeStep({ operator: combineOpEnum.INTERSECT });
    const { container, rerender } = render(<CombineNode {...defaultProps(step)} />);
    expect(
      container.querySelector('[data-region="lens"]')?.getAttribute("data-active"),
    ).toBe("true");

    const updated = makeStep({ operator: combineOpEnum.UNION });
    rerender(<CombineNode {...defaultProps(updated)} />);

    expect(
      container.querySelector('[data-region="left-only"]')?.getAttribute("data-active"),
    ).toBe("true");
    expect(
      container
        .querySelector('[data-region="right-only"]')
        ?.getAttribute("data-active"),
    ).toBe("true");
  });

  it("renders two input handles on the left + one output on the right", () => {
    const step = makeStep();
    render(<CombineNode {...defaultProps(step)} />);
    expect(screen.getByTestId("flow-handle-target-left")).toBeTruthy();
    expect(screen.getByTestId("flow-handle-target-left-secondary")).toBeTruthy();
    expect(screen.getByTestId("flow-handle-source-right")).toBeTruthy();
  });

  it("rings each input handle with the card token", () => {
    const step = makeStep();
    render(<CombineNode {...defaultProps(step)} />);
    for (const id of ["flow-handle-target-left", "flow-handle-target-left-secondary"]) {
      const handle = screen.getByTestId(id);
      expect(handle).toHaveClass("border-card");
      expect(handle.className).not.toContain("border-white");
    }
  });
});

describe("CombineNode names the operation, not the WDK question", () => {
  beforeEach(reset);

  it("names an imported combine by its operator", () => {
    const step = makeStep({
      searchName: "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
      displayName: "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
      operator: combineOpEnum.INTERSECT,
    });
    render(<CombineNode {...defaultProps(step)} />);
    expect(screen.getByTestId("node-title").textContent).toBe("Intersect");
  });

  it("names a minus combine by its operator", () => {
    const step = makeStep({
      searchName: "boolean_question_GeneRecordClasses_GeneRecordClass",
      displayName: "boolean_question_GeneRecordClasses_GeneRecordClass",
      operator: combineOpEnum.RMINUS,
    });
    render(<CombineNode {...defaultProps(step)} />);
    expect(screen.getByTestId("node-title").textContent).toBe("Right minus");
  });

  it("labels the operator badge with the name the title and menus use", () => {
    const step = makeStep({ displayName: "Secreted", operator: combineOpEnum.RMINUS });
    render(<CombineNode {...defaultProps(step)} />);
    expect(screen.getByTestId("combine-operator-badge").textContent).toBe(
      "Right minus",
    );
    expect(screen.queryByText(/NOT \(/)).toBeNull();
  });

  it("keeps a name the owner gave the combine", () => {
    const step = makeStep({
      searchName: "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
      displayName: "Secreted and essential",
    });
    render(<CombineNode {...defaultProps(step)} />);
    expect(screen.getByTestId("node-title").textContent).toBe("Secreted and essential");
  });
});
