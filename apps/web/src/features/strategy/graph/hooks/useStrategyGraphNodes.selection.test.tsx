// @vitest-environment jsdom
import { makeStep, makeStrategy } from "@/lib/types/fixtures";
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import type { ReactNode } from "react";
import { createElement } from "react";
import type { Strategy } from "@pathfinder/shared";
import { useStrategyGraphNodes } from "./useStrategyGraphNodes";

function strategyWith(fold: string): Strategy {
  return makeStrategy({
    id: "conv-1",
    name: "s",
    recordType: "transcript",
    steps: [
      makeStep({
        id: "step_a",
        displayName: "Step A",
        searchName: "GenesByMicroarray",
        parameters: { fold_change: { type: "string", value: fold } },
      }),
    ],
  });
}

const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(ReactFlowProvider, null, children);

describe("useStrategyGraphNodes - selected step tracks the live strategy", () => {
  // The editor footer compares form values against the selected step. When
  // selection held a frozen copy, a saved edit left the footer showing
  // "Edited: 1 change" forever because the copy still had the old value.
  it("reflects a parameter change made after selection", () => {
    const { result, rerender } = renderHook(
      ({ strategy }: { strategy: Strategy }) =>
        useStrategyGraphNodes({ strategy, siteId: "plasmodb", variant: "full" }),
      { initialProps: { strategy: strategyWith("1") }, wrapper },
    );

    act(() => result.current.setSelectedStep(result.current.editableSteps[0]!));
    expect(
      (result.current.selectedStep?.parameters as Record<string, { value: string }>)[
        "fold_change"
      ]?.value,
    ).toBe("1");

    rerender({ strategy: strategyWith("2") });
    expect(
      (result.current.selectedStep?.parameters as Record<string, { value: string }>)[
        "fold_change"
      ]?.value,
    ).toBe("2");
  });

  it("clears selection when the step disappears from the strategy", () => {
    const { result, rerender } = renderHook(
      ({ strategy }: { strategy: Strategy }) =>
        useStrategyGraphNodes({ strategy, siteId: "plasmodb", variant: "full" }),
      { initialProps: { strategy: strategyWith("1") }, wrapper },
    );
    act(() => result.current.setSelectedStep(result.current.editableSteps[0]!));
    expect(result.current.selectedStep).not.toBe(null);

    rerender({ strategy: { ...strategyWith("1"), steps: [] } });
    expect(result.current.selectedStep).toBe(null);
  });

  it("deselects when set to null", () => {
    const { result } = renderHook(
      () =>
        useStrategyGraphNodes({
          strategy: strategyWith("1"),
          siteId: "plasmodb",
          variant: "full",
        }),
      { wrapper },
    );
    act(() => result.current.setSelectedStep(result.current.editableSteps[0]!));
    act(() => result.current.setSelectedStep(null));
    expect(result.current.selectedStep).toBe(null);
  });
});
