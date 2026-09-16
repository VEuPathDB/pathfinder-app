// @vitest-environment jsdom
import { makeStrategy } from "@/lib/types/fixtures";
import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import { useStrategyGraphHandlers } from "./useStrategyGraphHandlers";

vi.mock("@/features/strategy/mutations", () => ({
  useAddStepMutation: () => ({ mutate: vi.fn() }),
  useUpdateStepMutation: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/features/strategy/graph/hooks/useDeleteOperation", () => ({
  useDeleteOperation: () => ({ requestDelete: vi.fn(), requestDeleteMany: vi.fn() }),
}));

const strategy = makeStrategy({ id: "conv-1", steps: [], recordType: "gene" });

function setup(selectedNodeIds: string[]) {
  return renderHook(
    ({ ids }: { ids: string[] }) =>
      useStrategyGraphHandlers({
        strategy,
        isCompact: false,
        editableSteps: [] as Step[],
        selectedStep: null,
        setSelectedStep: vi.fn(),
        selectedNodeIds: ids,
        startCombine: vi.fn(),
      }),
    { initialProps: { ids: selectedNodeIds } },
  );
}

describe("useStrategyGraphHandlers - ortholog transform", () => {
  it("captures the target step when opened", () => {
    const { result } = setup(["step_a"]);
    act(() => result.current.handleStartOrthologTransformFromSelection());
    expect(result.current.orthologTargetId).toBe("step_a");
  });

  // The regression: clicking the toolbar button clears ReactFlow's node
  // selection, so a render gate reading live selection closed the sheet
  // before it ever mounted - the button looked like a no-op.
  it("keeps the target after the selection is cleared", () => {
    const { result, rerender } = setup(["step_a"]);
    act(() => result.current.handleStartOrthologTransformFromSelection());
    rerender({ ids: [] });
    expect(result.current.orthologTargetId).toBe("step_a");
  });

  it("does nothing when no step is selected", () => {
    const { result } = setup([]);
    act(() => result.current.handleStartOrthologTransformFromSelection());
    expect(result.current.orthologTargetId).toBe(null);
  });

  it("does nothing when several steps are selected", () => {
    const { result } = setup(["step_a", "step_b"]);
    act(() => result.current.handleStartOrthologTransformFromSelection());
    expect(result.current.orthologTargetId).toBe(null);
  });

  it("is inert in compact mode", () => {
    const { result } = renderHook(() =>
      useStrategyGraphHandlers({
        strategy,
        isCompact: true,
        editableSteps: [] as Step[],
        selectedStep: null,
        setSelectedStep: vi.fn(),
        selectedNodeIds: ["step_a"],
        startCombine: vi.fn(),
      }),
    );
    act(() => result.current.handleStartOrthologTransformFromSelection());
    expect(result.current.orthologTargetId).toBe(null);
  });

  it("closing clears the captured target", () => {
    const { result } = setup(["step_a"]);
    act(() => result.current.handleStartOrthologTransformFromSelection());
    act(() => result.current.setOrthologTargetId(null));
    expect(result.current.orthologTargetId).toBe(null);
  });
});
