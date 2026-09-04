// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { Position } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

function setReducedMotion(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)" ? matches : false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => true,
  })) as typeof window.matchMedia;
}

import { StepEdge } from "./StepEdge";

const baseProps: EdgeProps = {
  id: "e1",
  source: "a",
  target: "b",
  sourceX: 0,
  sourceY: 0,
  targetX: 100,
  targetY: 100,
  sourcePosition: Position.Bottom,
  targetPosition: Position.Top,
  selected: false,
  animated: false,
  selectable: true,
  deletable: true,
  type: "step",
} as EdgeProps;

function renderEdge() {
  return render(
    <svg>
      <StepEdge {...baseProps} />
    </svg>,
  );
}

describe("StepEdge", () => {
  beforeEach(() => setReducedMotion(false));
  afterEach(() => cleanup());

  it("renders an SVG path with a generated d attribute", () => {
    const { container } = renderEdge();
    const paths = container.querySelectorAll('[data-testid="step-edge-e1"]');
    expect(paths).toHaveLength(1);
    expect(paths[0]).toHaveAttribute("d", expect.stringMatching(/^M[\d.,\s-]/));
  });

  it("animates pathLength from 0 to 1 when reduced-motion is off", () => {
    setReducedMotion(false);
    const { container } = renderEdge();
    const path = container.querySelector('[data-testid="step-edge-e1"]');
    expect(path).not.toBeNull();
    // motion writes the initial pathLength via stroke-dasharray during the
    // animation; the component is verified by the absence of a static
    // pathLength=1 value at first paint.
    const dasharray = path?.getAttribute("stroke-dasharray");
    expect(dasharray ?? "").not.toBe("");
  });

  it("skips animation when reduced-motion is on (no dash offset)", () => {
    setReducedMotion(true);
    const { container } = renderEdge();
    const path = container.querySelector('[data-testid="step-edge-e1"]');
    expect(path).not.toBeNull();
    // With reduced motion the path should render at full length immediately;
    // motion sets dash-array but the offset should be effectively 0.
    const offset = path?.getAttribute("stroke-dashoffset");
    expect(offset == null || offset === "0px" || offset === "0").toBe(true);
  });
});
