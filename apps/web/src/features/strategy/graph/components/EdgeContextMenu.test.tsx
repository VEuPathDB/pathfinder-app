// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Edge } from "@xyflow/react";
import { combineOpEnum, type Step } from "@pathfinder/shared";
import { EdgeContextMenu } from "./EdgeContextMenu";

const COMBINE_STEP: Step = {
  id: "step_combine",
  kind: "combine",
  displayName: "Combine",
  searchName: "",
  recordType: "gene",
  parameters: {},
  primaryInputStepId: "step_a",
  secondaryInputStepId: "step_b",
  operator: combineOpEnum.INTERSECT,
  isFiltered: false,
};

const SEARCH_STEP: Step = {
  id: "step_search",
  kind: "search",
  displayName: "Search",
  searchName: "GenesByTaxon",
  recordType: "gene",
  parameters: {},
  isFiltered: false,
};

const COMBINE_EDGE: Edge = {
  id: "e1",
  source: "step_a",
  target: "step_combine",
};
const SEARCH_EDGE: Edge = {
  id: "e2",
  source: "step_search",
  target: "step_search_2",
};

describe("EdgeContextMenu", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders operator grid for combine edges and fires onChangeOperator", () => {
    const onChange = vi.fn();
    render(
      <EdgeContextMenu
        edge={COMBINE_EDGE}
        x={100}
        y={100}
        steps={[COMBINE_STEP]}
        onDeleteEdge={vi.fn()}
        onChangeOperator={onChange}
        onClose={vi.fn()}
      />,
    );
    const grid = screen.getByTestId("edge-context-menu-operator-grid");
    expect(grid).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Set operator to Union/i));
    expect(onChange).toHaveBeenCalledWith("step_combine", combineOpEnum.UNION);
  });

  it("does not render operator grid for non-combine edges", () => {
    render(
      <EdgeContextMenu
        edge={SEARCH_EDGE}
        x={50}
        y={50}
        steps={[SEARCH_STEP]}
        onDeleteEdge={vi.fn()}
        onChangeOperator={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryAllByTestId("edge-context-menu-operator-grid")).toHaveLength(0);
    expect(screen.getByRole("menuitem", { name: /delete edge/i })).toBeVisible();
  });

  it("Delete edge fires onDeleteEdge", () => {
    const onDelete = vi.fn();
    render(
      <EdgeContextMenu
        edge={COMBINE_EDGE}
        x={100}
        y={100}
        steps={[COMBINE_STEP]}
        onDeleteEdge={onDelete}
        onChangeOperator={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("menuitem", { name: /delete edge/i }));
    expect(onDelete).toHaveBeenCalledWith(COMBINE_EDGE);
  });
});
