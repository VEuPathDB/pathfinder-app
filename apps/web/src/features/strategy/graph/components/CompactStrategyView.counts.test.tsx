// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Step, Strategy } from "@pathfinder/shared";

import { useStrategyStore } from "@/state/strategy/store";
import { CompactStrategyView } from "./CompactStrategyView";

/**
 * The real useStepSnapshot, deliberately unmocked: the sibling suite stubs it
 * to a constant, so only a test using the hook itself can see which object the
 * row hands it.
 */

const step = (overrides: Partial<Step> & { id: string }): Step => ({
  displayName: overrides.id,
  searchName: "GenesByTaxon",
  recordType: "gene",
  parameters: {},
  isFiltered: false,
  ...overrides,
});

const COUNTED: Strategy = {
  id: "s4",
  name: "Counted",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    step({ id: "step_x", displayName: "Search X", estimatedSize: 373 }),
    step({ id: "step_y", displayName: "Search Y", estimatedSize: 356 }),
    step({
      id: "step_z",
      displayName: "__combine__",
      searchName: "__combine__",
      operator: "UNION",
      primaryInputStepId: "step_x",
      secondaryInputStepId: "step_y",
      estimatedSize: 503,
    }),
  ],
  rootStepId: "step_z",
  isSaved: false,
} as Strategy;

function uncounted(): Strategy {
  return {
    ...COUNTED,
    steps: COUNTED.steps.map((s) =>
      s.id === "step_x" ? { ...s, estimatedSize: null } : s,
    ),
  };
}

function countIn(stepId: string): string | null {
  const row = screen.getByTestId(`compact-step-row-${stepId}`);
  return within(row).getByText(/^[\d,.]+$/).textContent;
}

describe("counts come straight from the wire", () => {
  // The strategy store is hydrated only once the graph canvas mounts. The list
  // must not wait for that, because the backend already sends a count per step.
  beforeEach(() => {
    useStrategyStore.setState({ stepLifecycleById: {} });
  });
  afterEach(cleanup);

  it("shows a leaf count with an empty store", () => {
    render(<CompactStrategyView strategy={COUNTED} />);

    expect(countIn("step_x")).toBe("373");
  });

  it("shows a combine count with an empty store", () => {
    render(<CompactStrategyView strategy={COUNTED} />);

    expect(countIn("step_z")).toBe("503");
  });

  it("shows no placeholder when every step has a count", () => {
    render(<CompactStrategyView strategy={COUNTED} />);

    expect(screen.queryByText("...")).toBe(null);
  });

  it("keeps the wire count when the store cached another one", () => {
    // The store holds what the canvas computed for itself. VEuPathDB owns the
    // count, and the server writes it through on every change.
    useStrategyStore.getState().applyStepCounts({ step_x: 999 });
    render(<CompactStrategyView strategy={COUNTED} />);

    expect(countIn("step_x")).toBe("373");
  });

  it("uses the store's count for a step the wire does not count", () => {
    useStrategyStore.getState().applyStepCounts({ step_x: 999 });
    render(<CompactStrategyView strategy={uncounted()} />);

    expect(countIn("step_x")).toBe("999");
  });

  it("still shows a placeholder for a step that has no count anywhere", () => {
    render(<CompactStrategyView strategy={uncounted()} />);

    expect(countIn("step_x")).toBe("...");
  });
});
