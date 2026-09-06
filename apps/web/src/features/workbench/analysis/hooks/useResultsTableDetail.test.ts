/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { createTestWrapper } from "@/lib/query/testing";

const mockGetRecordDetail = vi.fn();

vi.mock("@/features/workbench/analysis/api/stepResults", () => ({
  getRecordDetail: (...args: unknown[]) => mockGetRecordDetail(...args),
}));

import { useResultsTableDetail } from "./useResultsTableDetail";
import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";

describe("useResultsTableDetail", () => {
  const entityRef: EntityRef = { type: "experiment", id: "exp-1" };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch when expandedKey is null", () => {
    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(
      () =>
        useResultsTableDetail({
          entityRef,
          expandedKey: null,
          recordId: null,
        }),
      { wrapper: Wrapper },
    );

    expect(result.current.detail).toBeNull();
    expect(result.current.detailError).toBeNull();
    expect(result.current.detailLoading).toBe(false);
    expect(mockGetRecordDetail).not.toHaveBeenCalled();
  });

  it("fetches detail when expandedKey and recordId are set", async () => {
    const detail: RecordDetailResponse = {
      displayName: "G1",
      id: [{ name: "source_id", value: "G1" }],
      recordClassName: "TranscriptRecordClasses.TranscriptRecordClass",
      attributes: { gene_id: "G1" },
      attributeNames: { gene_id: "Gene ID" },
      tables: {},
      tableErrors: [],
    };
    mockGetRecordDetail.mockResolvedValueOnce(detail);

    const recordId: ClassifiedRecord["id"] = [{ name: "source_id", value: "G1" }];
    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(
      () =>
        useResultsTableDetail({
          entityRef,
          expandedKey: "row-1",
          recordId,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(result.current.detailLoading).toBe(false);
    });

    expect(result.current.detail).toEqual(detail);
    expect(result.current.detailError).toBeNull();
  });

  it("reports error when detail fetch fails", async () => {
    mockGetRecordDetail.mockRejectedValueOnce(new Error("server error"));

    const recordId: ClassifiedRecord["id"] = [{ name: "source_id", value: "G1" }];
    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(
      () =>
        useResultsTableDetail({
          entityRef,
          expandedKey: "row-1",
          recordId,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(result.current.detailLoading).toBe(false);
    });

    expect(result.current.detailError).toBe("server error");
    expect(result.current.detail).toBeNull();
  });
});
