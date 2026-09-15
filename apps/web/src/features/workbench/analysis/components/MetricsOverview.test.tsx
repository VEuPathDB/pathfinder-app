// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ExperimentMetrics } from "@pathfinder/shared";

vi.mock("@/lib/components/charts/EChart", () => ({
  EChart: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

import { TooltipProvider } from "@/components/ui/tooltip";
import { MetricsOverview } from "./MetricsOverview";

function metrics(): ExperimentMetrics {
  return {
    sensitivity: 0.8,
    specificity: 0.8,
    precision: 0.8,
    f1Score: 0.8,
    mcc: 0.6,
    balancedAccuracy: 0.8,
    confusionMatrix: {
      truePositives: 4,
      falsePositives: 1,
      trueNegatives: 4,
      falseNegatives: 1,
    },
    totalResults: 155,
  };
}

describe("MetricsOverview", () => {
  afterEach(cleanup);

  it("says the metrics are computed over the control genes", () => {
    render(
      <TooltipProvider>
        <MetricsOverview metrics={metrics()} />
      </TooltipProvider>,
    );

    expect(
      screen.getByText("Computed over the control genes, not the full result set."),
    ).toBeTruthy();
  });

  it("still reports each metric it was given", () => {
    render(
      <TooltipProvider>
        <MetricsOverview metrics={metrics()} />
      </TooltipProvider>,
    );

    const precision = screen
      .getByTestId("metrics-overview")
      .querySelector('[data-metric="Precision"]');
    expect(precision).toHaveTextContent("80.0%");
  });
});
