/**
 * @vitest-environment jsdom
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { Step, Strategy } from "@pathfinder/shared";

const applyOperationEndpointMock = vi.hoisted(() => vi.fn());
vi.mock("@pathfinder/shared/generated/hooks/useApplyOperationEndpoint", () => ({
  applyOperationEndpoint: applyOperationEndpointMock,
}));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}));

import { toast } from "sonner";
import { applyOperationEndpointMutationRequestSchema } from "@pathfinder/shared/generated/zod/applyOperationEndpointSchema";
import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import { useStrategyStore } from "@/state/strategy/store";
import { useApplyOperation } from "./useApplyOperation";
import { makeQueryHarness } from "./__tests__/strategyTestUtils";

function step(partial: Partial<Step> & { id: string; displayName: string }): Step {
  return { isFiltered: false, ...partial };
}

function makeStrategy(steps: Step[]): Strategy {
  return {
    id: "strategy-1",
    name: "Test",
    siteId: "plasmodb",
    recordType: "gene",
    steps,
    rootStepId: steps[steps.length - 1]?.id ?? null,
    isSaved: false,
    description: null,
    wdkStrategyId: null,
    wdkUrl: null,
    createdAt: "t",
    updatedAt: "t",
  };
}

beforeEach(() => {
  useStrategyStore.getState().clear();
  useStrategyStore.setState({ graphValidationStatus: {} });
  applyOperationEndpointMock.mockReset();
});

describe("useApplyOperation", () => {
  it("optimistically applies the op and POSTs the verb to /operations", async () => {
    const initial = makeStrategy([
      step({ id: "a", displayName: "A", searchName: "geneById", recordType: "gene" }),
    ]);
    const harness = makeQueryHarness(initial);
    applyOperationEndpointMock.mockResolvedValueOnce({
      ...initial,
      steps: [{ ...initial.steps[0]!, displayName: "Renamed" }],
    });

    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        op: { kind: "updateStepMeta", stepId: "a", displayName: "Renamed" },
      });
    });

    expect(applyOperationEndpointMock).toHaveBeenCalledTimes(1);
    const call = applyOperationEndpointMock.mock.calls[0];
    expect(call?.[0]).toBe("strategy-1");
    expect(call?.[1].op.kind).toBe("updateStepMeta");
    expect(harness.getStrategy("strategy-1")?.steps[0]?.displayName).toBe("Renamed");
  });

  it("rolls back optimistic state on server error and stores lastFailedOperation", async () => {
    const initial = makeStrategy([
      step({ id: "a", displayName: "A", searchName: "geneById", recordType: "gene" }),
    ]);
    const harness = makeQueryHarness(initial);
    applyOperationEndpointMock.mockRejectedValueOnce(new Error("boom"));

    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          op: { kind: "updateStepMeta", stepId: "a", displayName: "Renamed" },
        }),
      ).rejects.toThrow();
    });

    await waitFor(() => {
      expect(harness.getStrategy("strategy-1")?.steps[0]?.displayName).toBe("A");
      expect(useStrategyStore.getState().lastFailedOperation).not.toBeNull();
    });
  });

  it("says in one sentence which parameter kept a step from being saved", async () => {
    const initial = makeStrategy([
      step({ id: "a", displayName: "A", searchName: "GenesByOrthologs" }),
    ]);
    const harness = makeQueryHarness(initial);
    const body = {
      op: {
        kind: "updateStepParams",
        stepId: "a",
        parameters: { gene_result: { type: "input-step", stepId: "" } },
      },
    };
    applyOperationEndpointMock.mockImplementationOnce(() =>
      applyOperationEndpointMutationRequestSchema.parse(body),
    );

    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          op: {
            kind: "updateStepParams",
            stepId: "a",
            parameters: {
              isSyntenic: { type: "single-pick-vocabulary", value: "yes" },
            },
          },
        }),
      ).rejects.toThrow();
    });

    expect(toast.error).toHaveBeenCalledWith(
      "The step could not be saved: gene_result is missing a value",
    );
  });

  it("pushes a snapshot to the history slice on success", async () => {
    const initial = makeStrategy([
      step({ id: "a", displayName: "A", searchName: "geneById", recordType: "gene" }),
    ]);
    const harness = makeQueryHarness(initial);
    applyOperationEndpointMock.mockResolvedValueOnce(initial);

    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });
    expect(useStrategyStore.getState().undoStack.length).toBe(0);
    await act(async () => {
      await result.current.mutateAsync({
        op: { kind: "updateStepMeta", stepId: "a", displayName: "Renamed" },
      });
    });
    expect(useStrategyStore.getState().undoStack.length).toBe(1);
  });

  it("marks the step answers stale once the server answers the edit", async () => {
    const initial = makeStrategy([
      step({ id: "a", displayName: "A", searchName: "geneById", recordType: "gene" }),
    ]);
    const harness = makeQueryHarness(initial);
    const pageKey = [
      ...getStepRecordsQueryKey("strategy-1", "a", {
        siteId: "plasmodb",
        offset: 0,
        limit: 50,
      }),
      { wdkStepId: 22 },
    ];
    harness.client.setQueryData(pageKey, { records: [] });
    applyOperationEndpointMock.mockResolvedValueOnce(initial);

    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({
        op: { kind: "updateStepParams", stepId: "a", parameters: {} },
      });
    });

    expect(harness.client.getQueryState(pageKey)?.isInvalidated).toBe(true);
  });
});
