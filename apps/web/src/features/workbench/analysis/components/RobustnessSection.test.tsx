// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { BootstrapResult, ConfidenceInterval } from "@pathfinder/shared";
import { RobustnessSection } from "./RobustnessSection";

function makeCI(mean: number, lower: number, upper: number): ConfidenceInterval {
  return { lower, mean, upper, std: (upper - lower) / 4 };
}

function makeBootstrap(overrides: Partial<BootstrapResult> = {}): BootstrapResult {
  return {
    nIterations: 200,
    metricCis: {
      sensitivity: makeCI(0.85, 0.78, 0.91),
      specificity: makeCI(0.9, 0.85, 0.94),
      f1_score: makeCI(0.82, 0.75, 0.88),
    },
    ...overrides,
  };
}

describe("RobustnessSection", () => {
  afterEach(cleanup);

  it("renders the section header", () => {
    render(<RobustnessSection robustness={makeBootstrap()} />);
    expect(screen.getByText("Robustness & Uncertainty")).toBeTruthy();
  });

  it("displays bootstrap iteration count", () => {
    render(<RobustnessSection robustness={makeBootstrap()} />);
    expect(screen.getByText(/200 bootstrap iterations/)).toBeTruthy();
  });

  it("renders CI table with metric rows", () => {
    render(<RobustnessSection robustness={makeBootstrap()} />);
    expect(screen.getByText("Sensitivity")).toBeTruthy();
    expect(screen.getByText("Specificity")).toBeTruthy();
    expect(screen.getByText("F1 Score")).toBeTruthy();
  });

  it("displays mean values as percentages", () => {
    render(<RobustnessSection robustness={makeBootstrap()} />);
    expect(screen.getByText("85.0%")).toBeTruthy();
  });

  it("renders nothing when no classification CIs are present", () => {
    const { container } = render(
      <RobustnessSection robustness={makeBootstrap({ metricCis: {} })} />,
    );
    expect(container.innerHTML).toBe("");
  });
});
