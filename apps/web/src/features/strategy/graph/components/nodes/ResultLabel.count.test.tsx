// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import { ResultLabel } from "./ResultLabel";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";

const STEP: Step = {
  id: "s1",
  searchName: "GenesByOrthologs",
  displayName: "Orthologs",
  recordType: "transcript",
  isFiltered: false,
  status: "built",
};

function snapshot(estimatedSize: number | null): StepSnapshot {
  return {
    step: STEP,
    lifecycleState: "idle",
    estimatedSize,
    validationErrors: null,
    lastError: null,
    isBusy: false,
    isInvalid: false,
    isFailed: false,
    isDraft: false,
    wdkPushError: null,
  };
}

describe("ResultLabel count unit", () => {
  it("counts a transcript step in genes", () => {
    render(<ResultLabel step={STEP} snapshot={snapshot(31)} />);

    expect(screen.getByText("31 genes")).toBeInTheDocument();
  });

  it("names genes while the count is unknown", () => {
    render(<ResultLabel step={STEP} snapshot={snapshot(null)} />);

    expect(screen.getByText("? genes")).toBeInTheDocument();
  });
});
