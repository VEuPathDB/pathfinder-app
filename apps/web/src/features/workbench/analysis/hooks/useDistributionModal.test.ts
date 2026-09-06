/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";

const mockGetRecords = vi.fn();

vi.mock("@/features/workbench/analysis/api/stepResults", () => ({
  getRecords: (...args: unknown[]) => mockGetRecords(...args),
}));

import { useDistributionModal } from "./useDistributionModal";
import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";

describe("useDistributionModal", () => {
  const entityRef: EntityRef = { type: "experiment", id: "exp-1" };
  const selectedAttr = "organism";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts with null modalValue and empty records", () => {
    const { result } = renderHook(() => useDistributionModal(entityRef, selectedAttr));
    expect(result.current.modalValue).toBeNull();
    expect(result.current.modalRecords).toEqual([]);
    expect(result.current.loadingModal).toBe(false);
  });

  it("handleBarClick sets modalValue and fetches records", async () => {
    const records: ClassifiedRecord[] = [
      {
        displayName: "G1",
        id: [{ name: "source_id", value: "G1" }],
        recordClassName: "transcript",
        attributes: { gene_id: "G1" },
        tables: {},
        tableErrors: [],
      },
    ];
    mockGetRecords.mockResolvedValueOnce({ records, meta: {} });

    const { result } = renderHook(() => useDistributionModal(entityRef, selectedAttr));

    await act(async () => {
      result.current.handleBarClick("Plasmodium falciparum");
    });

    await waitFor(() => {
      expect(result.current.loadingModal).toBe(false);
    });

    expect(result.current.modalValue).toBe("Plasmodium falciparum");
    expect(result.current.modalRecords).toEqual(records);
    expect(mockGetRecords).toHaveBeenCalledWith(entityRef, {
      attributes: [selectedAttr, "gene_product"],
      filterAttribute: selectedAttr,
      filterValue: "Plasmodium falciparum",
      limit: 500,
    });
  });

  it("closeModal resets modalValue to null", async () => {
    mockGetRecords.mockResolvedValueOnce({ records: [], meta: {} });

    const { result } = renderHook(() => useDistributionModal(entityRef, selectedAttr));

    await act(async () => {
      result.current.handleBarClick("someValue");
    });

    await waitFor(() => {
      expect(result.current.modalValue).toBe("someValue");
    });

    act(() => {
      result.current.closeModal();
    });

    expect(result.current.modalValue).toBeNull();
  });

  it("sets empty records on fetch error", async () => {
    mockGetRecords.mockRejectedValueOnce(new Error("network error"));

    const { result } = renderHook(() => useDistributionModal(entityRef, selectedAttr));

    await act(async () => {
      result.current.handleBarClick("value");
    });

    await waitFor(() => {
      expect(result.current.loadingModal).toBe(false);
    });

    expect(result.current.modalRecords).toEqual([]);
  });
});
