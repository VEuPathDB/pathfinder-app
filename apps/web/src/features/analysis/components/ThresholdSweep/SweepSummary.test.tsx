// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ThresholdSweepPoint } from "@/features/analysis/api/compute";
import { SweepSummary } from "./SweepSummary";

const point: ThresholdSweepPoint = {
  value: 0.5,
  metrics: {
    sensitivity: 0.8,
    specificity: 0.7,
    precision: 0.6,
    f1Score: 0.69,
    mcc: 0.4,
    balancedAccuracy: 0.75,
    totalResults: 120,
    falsePositiveRate: 0.3,
  },
};

describe("SweepSummary", () => {
  it("reports failed points through the warning token", () => {
    render(
      <SweepSummary
        points={[point]}
        parameter="min_score"
        sweepType="numeric"
        formatValue={(v) => String(v)}
        failedCount={2}
      />,
    );
    const notice = screen.getByText(/2 points failed/);
    expect(notice).toHaveClass("text-warning");
    expect(notice.className).not.toContain("amber");
  });

  it("shows no failure line when every point succeeded", () => {
    render(
      <SweepSummary
        points={[point]}
        parameter="min_score"
        sweepType="numeric"
        formatValue={(v) => String(v)}
        failedCount={0}
      />,
    );
    expect(screen.queryAllByText(/failed \(timeout or WDK/)).toHaveLength(0);
  });
});
