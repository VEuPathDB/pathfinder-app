// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { Step, Strategy } from "@strategist/shared";

const pushStrategyMock = vi.hoisted(() => vi.fn());
vi.mock("@strategist/shared/generated/hooks/usePushStrategy", () => ({
  pushStrategy: pushStrategyMock,
}));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}));

import { useDeleteOperation } from "./useDeleteOperation";
import { makeQueryHarness } from "@/features/strategy/mutations/__tests__/strategyTestUtils";
import { useStrategyStore } from "@/state/strategy/store";

function step(partial: Partial<Step> & { id: string }): Step {
  return {
    isFiltered: false,
    displayName: partial.id,
    ...partial,
  };
}

function strategy(steps: Step[], rootStepId: string | null = null): Strategy {
  return {
    id: "s",
    name: "T",
    siteId: "plasmodb",
    recordType: "gene",
    steps,
    rootStepId,
    isSaved: false,
    description: null,
    wdkStrategyId: null,
    wdkUrl: null,
    createdAt: "t",
    updatedAt: "t",
  };
}

beforeEach(() => {
  pushStrategyMock.mockReset();
  pushStrategyMock.mockResolvedValue({
    id: "s",
    name: "T",
    steps: [],
    siteId: "plasmodb",
  });
  useStrategyStore.setState({ graphValidationStatus: {} });
});

describe("useDeleteOperation.requestDelete", () => {
  it("unambiguous (sole leaf): applies and pushes immediately, no dialog", async () => {
    const initial = strategy([step({ id: "a" })], "a");
    const harness = makeQueryHarness(initial);
    const { result } = renderHook(() => useDeleteOperation("s"), {
      wrapper: harness.wrapper,
    });

    act(() => {
      result.current.requestDelete("a");
    });

    expect(result.current.dialogProps).toBeNull();
    expect(harness.getStrategy("s")?.steps).toEqual([]);
  });

  it("ambiguous (leaf of combine): opens dialog with all three choices", () => {
    const initial = strategy(
      [
        step({ id: "a" }),
        step({ id: "b" }),
        step({
          id: "c",
          primaryInputStepId: "a",
          secondaryInputStepId: "b",
          kind: "combine",
        }),
      ],
      "c",
    );
    const harness = makeQueryHarness(initial);
    const { result } = renderHook(() => useDeleteOperation("s"), {
      wrapper: harness.wrapper,
    });

    act(() => {
      result.current.requestDelete("a");
    });

    expect(result.current.dialogProps).not.toBeNull();
    expect(result.current.dialogProps?.choices.map((c) => c.resolution)).toEqual([
      "collapse-combine",
      "orphan-sibling",
      "delete-subtree",
    ]);
  });

  it("ambiguous: dialog onConfirm with chosen resolution applies and pushes", async () => {
    const initial = strategy(
      [
        step({ id: "a" }),
        step({ id: "b" }),
        step({
          id: "c",
          primaryInputStepId: "a",
          secondaryInputStepId: "b",
          kind: "combine",
        }),
      ],
      "c",
    );
    const harness = makeQueryHarness(initial);
    const { result, rerender } = renderHook(() => useDeleteOperation("s"), {
      wrapper: harness.wrapper,
    });

    act(() => {
      result.current.requestDelete("a");
    });
    rerender();
    expect(result.current.dialogProps).not.toBeNull();

    // Caller invokes onConfirm with the chosen resolution (what the dialog
    // delegates on Apply). Verifies the wire path independently of the
    // dialog's own UI-level interactions.
    act(() => {
      result.current.dialogProps!.onConfirm("collapse-combine");
    });

    await waitFor(() => {
      const after = harness.getStrategy("s");
      expect(after?.steps.map((x) => x.id).sort()).toEqual(["b"]);
    });
  });

  it("dialog onOpenChange(false) without confirm: no push, no mutation", () => {
    const initial = strategy(
      [
        step({ id: "a" }),
        step({ id: "b" }),
        step({
          id: "c",
          primaryInputStepId: "a",
          secondaryInputStepId: "b",
          kind: "combine",
        }),
      ],
      "c",
    );
    const harness = makeQueryHarness(initial);
    const { result, rerender } = renderHook(() => useDeleteOperation("s"), {
      wrapper: harness.wrapper,
    });

    act(() => {
      result.current.requestDelete("a");
    });
    rerender();
    expect(result.current.dialogProps).not.toBeNull();

    act(() => {
      result.current.dialogProps!.onOpenChange(false);
    });
    rerender();
    expect(result.current.dialogProps).toBeNull();
    expect(harness.getStrategy("s")?.steps.length).toBe(3);
    expect(pushStrategyMock).not.toHaveBeenCalled();
  });
});

describe("useDeleteOperation.requestDeleteMany", () => {
  it("skipConfirm=true: applies defaults to all ids in a single push", () => {
    const initial = strategy([step({ id: "a" }), step({ id: "b" })], null);
    const harness = makeQueryHarness(initial);
    const { result } = renderHook(() => useDeleteOperation("s"), {
      wrapper: harness.wrapper,
    });

    act(() => {
      result.current.requestDeleteMany(["a", "b"], { skipConfirm: true });
    });

    expect(result.current.dialogProps).toBeNull();
    expect(harness.getStrategy("s")?.steps).toEqual([]);
  });
});
