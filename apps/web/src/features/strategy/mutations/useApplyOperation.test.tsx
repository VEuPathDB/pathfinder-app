/**
 * @vitest-environment jsdom
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import type { Step, Strategy } from "@pathfinder/shared";

const applyOperationEndpointMock = vi.hoisted(() => vi.fn());
vi.mock("@pathfinder/shared/generated/hooks/useApplyOperationEndpoint", () => ({
  applyOperationEndpoint: applyOperationEndpointMock,
}));
const getStrategyMock = vi.hoisted(() => vi.fn());
vi.mock("@pathfinder/shared/generated/hooks/useGetStrategy", () => ({
  getStrategy: getStrategyMock,
}));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}));

import { toast } from "sonner";
import { applyOperationEndpointMutationRequestSchema } from "@pathfinder/shared/generated/zod/applyOperationEndpointSchema";
import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import { APIError } from "@/lib/api/http";
import { strategyQueryOptions } from "@/lib/api/strategy";
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

const REFUSAL =
  "This chat is still answering. Make this edit once the reply has finished.";

function refusedEdit(): APIError {
  return new APIError("HTTP 409 Conflict", {
    status: 409,
    statusText: "Conflict",
    url: "/api/v1/conversations/strategy-1/operations",
    data: {
      title: "Cannot edit this strategy now",
      status: 409,
      code: "EDIT_REFUSED",
      detail: REFUSAL,
    },
  });
}

function rename(displayName: string) {
  return { op: { kind: "updateStepMeta" as const, stepId: "a", displayName } };
}

beforeEach(() => {
  useStrategyStore.getState().clear();
  useStrategyStore.setState({ graphValidationStatus: {} });
  applyOperationEndpointMock.mockReset();
  getStrategyMock.mockReset();
  vi.mocked(toast.error).mockClear();
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

  it("sends an edit while a step of the strategy fails its check", async () => {
    const initial = makeStrategy([
      step({
        id: "a",
        displayName: "A",
        searchName: "GenesByTaxon",
        recordType: "gene",
      }),
    ]);
    const harness = makeQueryHarness(initial);
    useStrategyStore.getState().setGraphValidationStatus("strategy-1", true);
    const fix = {
      kind: "updateStepParams" as const,
      stepId: "a",
      parameters: {
        organism: {
          type: "multi-pick-vocabulary" as const,
          values: ["Plasmodium falciparum 3D7"],
        },
      },
    };
    applyOperationEndpointMock.mockResolvedValueOnce(initial);

    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({ op: fix });
    });

    expect(applyOperationEndpointMock).toHaveBeenCalledTimes(1);
    expect(applyOperationEndpointMock.mock.calls[0]?.[1].op.kind).toBe(
      "updateStepParams",
    );
    expect(toast.warning).not.toHaveBeenCalled();
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

  it("leaves the pending state and says what the site answered when a save fails", async () => {
    const harness = makeQueryHarness(
      makeStrategy([step({ id: "a", displayName: "A", searchName: "GenesByGoTerm" })]),
    );
    applyOperationEndpointMock.mockRejectedValueOnce(
      new APIError("HTTP 502 Bad Gateway", {
        status: 502,
        statusText: "Bad Gateway",
        url: "/api/v1/conversations/strategy-1/operations",
        data: { title: "VectorBase did not answer.", status: 502, code: "WDK_ERROR" },
      }),
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
            parameters: { go_term: { type: "string", value: "GO:0016301" } },
          },
        }),
      ).rejects.toThrow();
    });

    await waitFor(() => {
      expect([result.current.isPending, result.current.isError]).toEqual([false, true]);
    });
    expect(toast.error).toHaveBeenCalledWith("VectorBase did not answer.");
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

  it("says why a busy thread refused the edit and takes the edit back", async () => {
    const initial = makeStrategy([step({ id: "a", displayName: "A" })]);
    const harness = makeQueryHarness(initial);
    applyOperationEndpointMock.mockRejectedValueOnce(refusedEdit());
    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });

    await act(async () => {
      await expect(result.current.mutateAsync(rename("Renamed"))).rejects.toThrow();
    });

    expect(toast.error).toHaveBeenCalledWith(REFUSAL);
    expect(harness.getStrategy("strategy-1")).toEqual(initial);
    expect(useStrategyStore.getState().undoStack).toEqual([]);
  });

  it("shows what the server holds after every queued edit is refused", async () => {
    const initial = makeStrategy([step({ id: "a", displayName: "A" })]);
    const harness = makeQueryHarness(initial);
    applyOperationEndpointMock
      .mockRejectedValueOnce(refusedEdit())
      .mockRejectedValueOnce(refusedEdit());
    getStrategyMock.mockResolvedValue(
      makeStrategy([step({ id: "a", displayName: "Written by the turn" })]),
    );
    const { result } = renderHook(
      () => {
        useQuery(strategyQueryOptions("strategy-1"));
        return useApplyOperation("strategy-1");
      },
      { wrapper: harness.wrapper },
    );

    await act(async () => {
      await Promise.allSettled([
        result.current.mutateAsync(rename("First")),
        result.current.mutateAsync(rename("Second")),
      ]);
    });

    await waitFor(() => {
      expect(harness.getStrategy("strategy-1")?.steps[0]?.displayName).toBe(
        "Written by the turn",
      );
    });
    expect(useStrategyStore.getState().undoStack).toEqual([]);
  });

  it("keeps the undo entry of an edit that follows a refused one", async () => {
    const initial = makeStrategy([step({ id: "a", displayName: "A" })]);
    const harness = makeQueryHarness(initial);
    let refuseFirst: (reason: Error) => void = () => undefined;
    applyOperationEndpointMock
      .mockReturnValueOnce(
        new Promise<Strategy>((_resolve, reject) => {
          refuseFirst = reject;
        }),
      )
      .mockResolvedValueOnce(makeStrategy([step({ id: "a", displayName: "Second" })]));
    const { result } = renderHook(() => useApplyOperation("strategy-1"), {
      wrapper: harness.wrapper,
    });

    let both = Promise.resolve<unknown>(null);
    await act(async () => {
      both = Promise.allSettled([
        result.current.mutateAsync(rename("First")),
        result.current.mutateAsync(rename("Second")),
      ]);
      await Promise.resolve();
    });
    const [, kept] = useStrategyStore.getState().undoStack;
    expect(kept).toBeDefined();

    await act(async () => {
      refuseFirst(refusedEdit());
      await both;
    });

    expect(useStrategyStore.getState().undoStack).toEqual([kept]);
  });
});
