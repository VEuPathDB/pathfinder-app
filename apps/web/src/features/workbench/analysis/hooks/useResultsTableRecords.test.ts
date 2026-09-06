/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { createTestWrapper } from "@/lib/query/testing";

const mockGetRecords = vi.fn();

vi.mock("@/features/workbench/analysis/api/stepResults", () => ({
  getRecords: (...args: unknown[]) => mockGetRecords(...args),
}));

import { useResultsTableRecords } from "./useResultsTableRecords";
import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";

function makeRecordsResponse(count: number) {
  return {
    records: Array.from({ length: count }, (_, i) => ({
      id: [{ name: "source_id", value: `GENE_${i}` }],
      attributes: { gene_id: `GENE_${i}` },
    })),
    meta: {
      totalCount: count,
      displayTotalCount: count,
      responseCount: count,
      pagination: { offset: 0, numRecords: 25 },
      attributes: ["gene_id"],
      tables: [],
    },
  };
}

describe("useResultsTableRecords", () => {
  const entityRef: EntityRef = { type: "experiment", id: "exp-1" };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches records when attributes are non-empty", async () => {
    mockGetRecords.mockResolvedValueOnce(makeRecordsResponse(3));

    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(
      () =>
        useResultsTableRecords({
          entityRef,
          attributes: ["gene_id", "organism"],
          sorting: [],
          pageIndex: 0,
          pageSize: 25,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.records).toHaveLength(3);
    expect(result.current.meta?.totalCount).toBe(3);
  });

  it("does not fetch when attributes list is empty", () => {
    const { Wrapper } = createTestWrapper();
    renderHook(
      () =>
        useResultsTableRecords({
          entityRef,
          attributes: [],
          sorting: [],
          pageIndex: 0,
          pageSize: 25,
        }),
      { wrapper: Wrapper },
    );

    expect(mockGetRecords).not.toHaveBeenCalled();
  });

  it("translates SortingState ASC into sort/dir query params", async () => {
    mockGetRecords.mockResolvedValueOnce(makeRecordsResponse(1));

    const { Wrapper } = createTestWrapper();
    renderHook(
      () =>
        useResultsTableRecords({
          entityRef,
          attributes: ["gene_id"],
          sorting: [{ id: "gene_id", desc: false }],
          pageIndex: 0,
          pageSize: 25,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    const call = mockGetRecords.mock.calls[0];
    expect(call?.[1]).toMatchObject({ sort: "gene_id", dir: "ASC" });
  });

  it("translates SortingState DESC into sort/dir query params", async () => {
    mockGetRecords.mockResolvedValueOnce(makeRecordsResponse(1));

    const { Wrapper } = createTestWrapper();
    renderHook(
      () =>
        useResultsTableRecords({
          entityRef,
          attributes: ["gene_id"],
          sorting: [{ id: "gene_id", desc: true }],
          pageIndex: 0,
          pageSize: 25,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    const call = mockGetRecords.mock.calls[0];
    expect(call?.[1]).toMatchObject({ sort: "gene_id", dir: "DESC" });
  });

  it("computes offset from pageIndex * pageSize", async () => {
    mockGetRecords.mockResolvedValueOnce(makeRecordsResponse(1));

    const { Wrapper } = createTestWrapper();
    renderHook(
      () =>
        useResultsTableRecords({
          entityRef,
          attributes: ["gene_id"],
          sorting: [],
          pageIndex: 3,
          pageSize: 25,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(mockGetRecords).toHaveBeenCalledTimes(1);
    });

    const call = mockGetRecords.mock.calls[0];
    expect(call?.[1]).toMatchObject({ offset: 75, limit: 25 });
  });

  it("reports error on fetch failure", async () => {
    mockGetRecords.mockRejectedValueOnce(new Error("Network error"));

    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(
      () =>
        useResultsTableRecords({
          entityRef,
          attributes: ["gene_id"],
          sorting: [],
          pageIndex: 0,
          pageSize: 25,
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe("Network error");
  });
});
