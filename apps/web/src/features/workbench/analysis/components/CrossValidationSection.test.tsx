// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { CrossValidationResult, ExperimentMetrics } from "@pathfinder/shared";
import { CrossValidationSection } from "./CrossValidationSection";

function makeMetrics(overrides: Partial<ExperimentMetrics> = {}): ExperimentMetrics {
  return {
    confusionMatrix: {
      truePositives: 8,
      falsePositives: 2,
      trueNegatives: 18,
      falseNegatives: 2,
    },
    sensitivity: 0.8,
    specificity: 0.9,
    precision: 0.8,
    negativePredictiveValue: 0.9,
    falsePositiveRate: 0.1,
    falseNegativeRate: 0.2,
    f1Score: 0.8,
    mcc: 0.7,
    balancedAccuracy: 0.85,
    youdensJ: 0.7,
    totalResults: 10,
    totalPositives: 10,
    totalNegatives: 20,
    ...overrides,
  };
}

function makeCVResult(
  overrides: Partial<CrossValidationResult> = {},
): CrossValidationResult {
  return {
    k: 5,
    folds: [
      {
        foldIndex: 0,
        metrics: makeMetrics({ sensitivity: 0.9, specificity: 0.85, f1Score: 0.87 }),
        positiveControlIds: [],
        negativeControlIds: [],
      },
      {
        foldIndex: 1,
        metrics: makeMetrics({ sensitivity: 0.8, specificity: 0.9, f1Score: 0.84 }),
        positiveControlIds: [],
        negativeControlIds: [],
      },
      {
        foldIndex: 2,
        metrics: makeMetrics({ sensitivity: 0.85, specificity: 0.88, f1Score: 0.86 }),
        positiveControlIds: [],
        negativeControlIds: [],
      },
      {
        foldIndex: 3,
        metrics: makeMetrics({ sensitivity: 0.75, specificity: 0.92, f1Score: 0.82 }),
        positiveControlIds: [],
        negativeControlIds: [],
      },
      {
        foldIndex: 4,
        metrics: makeMetrics({ sensitivity: 0.88, specificity: 0.87, f1Score: 0.87 }),
        positiveControlIds: [],
        negativeControlIds: [],
      },
    ],
    meanMetrics: makeMetrics({
      sensitivity: 0.836,
      specificity: 0.884,
      f1Score: 0.852,
    }),
    stdMetrics: { sensitivity: 0.057, specificity: 0.026, f1Score: 0.02 },
    overfittingScore: 0.12,
    overfittingLevel: "low",
    ...overrides,
  };
}

describe("CrossValidationSection", () => {
  afterEach(cleanup);

  it("renders the section header", () => {
    render(<CrossValidationSection cv={makeCVResult()} />);
    expect(screen.getByText("K-Fold Cross-Validation")).toBeTruthy();
  });

  it("displays fold count", () => {
    render(<CrossValidationSection cv={makeCVResult()} />);
    expect(screen.getByText(/5-fold/i)).toBeTruthy();
  });

  it("shows overfitting score with low-level indicator", () => {
    render(<CrossValidationSection cv={makeCVResult({ overfittingLevel: "low" })} />);
    expect(screen.getByText("Low")).toBeTruthy();
  });

  it("shows overfitting score with high-level indicator", () => {
    render(
      <CrossValidationSection
        cv={makeCVResult({ overfittingScore: 0.65, overfittingLevel: "high" })}
      />,
    );
    expect(screen.getByText("High")).toBeTruthy();
  });

  it("shows overfitting score with moderate-level indicator", () => {
    render(
      <CrossValidationSection
        cv={makeCVResult({ overfittingScore: 0.35, overfittingLevel: "moderate" })}
      />,
    );
    expect(screen.getByText("Moderate")).toBeTruthy();
  });

  it("renders per-fold metrics table with correct number of rows", () => {
    render(<CrossValidationSection cv={makeCVResult()} />);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    // 1 header + 5 body rows = 6
    expect(rows.length).toBe(6);
  });

  it("renders fold sensitivity values in the table", () => {
    render(<CrossValidationSection cv={makeCVResult()} />);
    // Fold 0 sensitivity 0.9 and fold 1 specificity 0.9 both render as "90.0%"
    const matches = screen.getAllByText("90.0%");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("displays mean and std summary", () => {
    render(<CrossValidationSection cv={makeCVResult()} />);
    // Mean sensitivity = 0.836 => "83.6%"
    expect(screen.getByText(/83\.6%/)).toBeTruthy();
  });
});
