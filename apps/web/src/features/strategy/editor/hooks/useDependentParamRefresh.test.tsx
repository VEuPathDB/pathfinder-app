/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ParamSpec } from "@pathfinder/shared";

const refreshDependentParamsMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/sites", () => ({
  refreshDependentParams: refreshDependentParamsMock,
}));

const toastWarningMock = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({
  toast: { warning: toastWarningMock, error: vi.fn(), success: vi.fn() },
}));

import { useDependentParamRefresh } from "./useDependentParamRefresh";

function spec(overrides: Partial<ParamSpec>): ParamSpec {
  return {
    name: "p",
    displayName: "P",
    type: "string",
    allowEmptyValue: true,
    allowMultipleValues: false,
    multiPick: false,
    minSelectedCount: null,
    maxSelectedCount: null,
    countOnlyLeaves: false,
    initialDisplayValue: null,
    vocabulary: null,
    min: null,
    max: null,
    increment: null,
    isNumber: false,
    displayType: null,
    isVisible: true,
    group: null,
    help: null,
    ...overrides,
  };
}

const ORGANISM_SPEC = spec({
  name: "organism",
  type: "single-pick-vocabulary",
  dependentParams: ["gene_list"],
  vocabulary: [
    ["A", "A", null],
    ["B", "B", null],
  ],
});

const GENE_LIST_SPEC = spec({
  name: "gene_list",
  type: "multi-pick-vocabulary",
  allowMultipleValues: true,
  vocabulary: [
    ["G1", "G1", null],
    ["G2", "G2", null],
  ],
});

const INDEPENDENT_SPEC = spec({ name: "free_text" });

beforeEach(() => {
  refreshDependentParamsMock.mockReset();
  toastWarningMock.mockReset();
});

describe("useDependentParamRefresh", () => {
  it("does not fire when an independent param changes", async () => {
    const { result } = renderHook(() =>
      useDependentParamRefresh({
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        specs: [ORGANISM_SPEC, GENE_LIST_SPEC, INDEPENDENT_SPEC],
      }),
    );

    act(() => {
      result.current.handleFieldChange("free_text", {});
    });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(refreshDependentParamsMock).not.toHaveBeenCalled();
  });

  it("fires when a parent param with dependentParams changes", async () => {
    refreshDependentParamsMock.mockResolvedValue([
      spec({
        name: "gene_list",
        vocabulary: [
          ["NEW1", "NEW1", null],
          ["NEW2", "NEW2", null],
        ],
      }),
    ]);

    const { result } = renderHook(() =>
      useDependentParamRefresh({
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        specs: [ORGANISM_SPEC, GENE_LIST_SPEC],
      }),
    );

    act(() => {
      result.current.handleFieldChange("organism", { organism: "A" });
    });

    await waitFor(() => {
      expect(refreshDependentParamsMock).toHaveBeenCalledWith(
        "plasmodb",
        "transcript",
        "GenesByTaxon",
        "organism",
        { organism: { type: "single-pick-vocabulary", value: "A" } },
      );
    });

    await waitFor(() => {
      expect(result.current.dependentOptions["gene_list"]).toBeDefined();
      expect(result.current.dependentOptions["gene_list"]?.[0]?.value).toBe("NEW1");
    });
  });

  it("leaves a parameter with no value out of the context it sends", async () => {
    refreshDependentParamsMock.mockResolvedValue([]);

    const { result } = renderHook(() =>
      useDependentParamRefresh({
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        specs: [ORGANISM_SPEC, GENE_LIST_SPEC],
      }),
    );

    act(() => {
      result.current.handleFieldChange("organism", { organism: "A", gene_list: [] });
    });

    await waitFor(() => {
      expect(refreshDependentParamsMock).toHaveBeenCalledWith(
        "plasmodb",
        "transcript",
        "GenesByTaxon",
        "organism",
        { organism: { type: "single-pick-vocabulary", value: "A" } },
      );
    });
  });

  it("clears a stale dependent value when no longer valid and toasts", async () => {
    refreshDependentParamsMock.mockResolvedValue([
      spec({
        name: "gene_list",
        vocabulary: [
          ["X1", "X1", null],
          ["X2", "X2", null],
        ],
      }),
    ]);

    const onClearStaleValue = vi.fn();
    const { result } = renderHook(() =>
      useDependentParamRefresh({
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        specs: [ORGANISM_SPEC, GENE_LIST_SPEC],
        onClearStaleValue,
      }),
    );

    act(() => {
      result.current.handleFieldChange("organism", {
        organism: "A",
        gene_list: ["G1"],
      });
    });

    await waitFor(() => {
      expect(onClearStaleValue).toHaveBeenCalledWith("gene_list");
    });
    expect(toastWarningMock).toHaveBeenCalledWith(
      expect.stringMatching(/Updated options/i),
    );
  });

  it("captures errors in dependentErrors when the API call fails", async () => {
    refreshDependentParamsMock.mockRejectedValue(new Error("Network failure"));

    const { result } = renderHook(() =>
      useDependentParamRefresh({
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        specs: [ORGANISM_SPEC, GENE_LIST_SPEC],
      }),
    );

    act(() => {
      result.current.handleFieldChange("organism", { organism: "A" });
    });

    await waitFor(() => {
      expect(result.current.dependentErrors["gene_list"]).toBe("Network failure");
    });
    expect(result.current.dependentLoading["gene_list"]).toBe(false);
  });
});
