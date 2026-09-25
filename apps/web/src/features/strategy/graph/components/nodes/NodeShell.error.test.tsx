// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";

import { useStrategyStore } from "@/state/strategy/store";
import { NodeShell } from "./NodeShell";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";

const LONG_ERROR =
  "Cannot be saved: Failed to load search metadata: VEuPathDB service error: " +
  "Request failed after retries: Server error '500 Internal Server Error' for " +
  "url 'https://plasmodb.org/plasmo/service/record-types/transcript/searches/" +
  "GenesByOrthologPattern?expandParams=true'";

function step(overrides: Partial<Step> = {}): Step {
  return {
    id: "step_1",
    displayName: "Genes by ortholog pattern",
    searchName: "GenesByOrthologPattern",
    recordType: "gene",
    parameters: {},
    isFiltered: false,
    estimatedSize: null,
    ...overrides,
  };
}

function Shell({ s }: { s: Step }) {
  const snapshot = useStepSnapshot(s);
  return (
    <NodeShell
      kind="search"
      step={s}
      selected={false}
      width={168}
      height={64}
      snapshot={snapshot}
    />
  );
}

function renderFailed(s: Step = step()) {
  useStrategyStore.setState({ stepLifecycleById: {} });
  useStrategyStore.getState().applyStepValidationErrors({ [s.id]: LONG_ERROR });
  return render(<Shell s={s} />);
}

describe("a step that failed to validate", () => {
  beforeEach(() => useStrategyStore.setState({ stepLifecycleById: {} }));
  afterEach(cleanup);

  it("still shows the step name", () => {
    renderFailed();

    expect(screen.getByTestId("node-title")).toHaveTextContent(
      "Genes by ortholog pattern",
    );
  });

  it("does not print the error over the node", () => {
    const { container } = renderFailed();

    expect(container.textContent).not.toContain("500 Internal Server Error");
  });

  it("shows an unknown count rather than nothing", () => {
    renderFailed();

    expect(screen.getByText(/genes/)).toHaveTextContent("? genes");
  });

  it("keeps the red corner dot", () => {
    const { container } = renderFailed();

    expect(container.querySelectorAll('[data-corner-dot="error"]')).toHaveLength(1);
  });

  it("carries the error on the dot for a popup to show", () => {
    renderFailed();

    expect(
      screen.getByTestId("node-error-trigger").getAttribute("aria-label"),
    ).toContain("Cannot be saved");
  });

  it("keeps a real name even while failed", () => {
    renderFailed(step({ displayName: "My step" }));

    expect(screen.getByTestId("node-title").textContent).toBe("My step");
  });
});

describe("a healthy step", () => {
  beforeEach(() => useStrategyStore.setState({ stepLifecycleById: {} }));
  afterEach(cleanup);

  it("shows its count", () => {
    render(<Shell s={step({ estimatedSize: 132 })} />);

    expect(screen.getByText(/genes/)).toHaveTextContent("132 genes");
  });

  it("has no error dot", () => {
    const { container } = render(<Shell s={step({ estimatedSize: 132 })} />);

    expect(container.querySelectorAll('[data-corner-dot="error"]')).toHaveLength(0);
  });

  it("offers no error popup", () => {
    render(<Shell s={step({ estimatedSize: 132 })} />);

    expect(screen.queryByTestId("node-error-trigger")).toBe(null);
  });
});
