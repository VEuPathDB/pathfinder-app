/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { createTestWrapper } from "@/lib/query/testing";
import { APIError } from "@/lib/api/http";

vi.mock("@/lib/api/sites", () => ({
  getParamSpecs: vi.fn(),
  paramSpecsOptions: () => ({
    queryKey: ["param-specs-simple"] as const,
    queryFn: async () => [],
    enabled: false,
  }),
}));

import { getParamSpecs } from "@/lib/api/sites";
import { useParamSpecs } from "./useParamSpecs";

const getParamSpecsMock = vi.mocked(getParamSpecs);

beforeEach(() => {
  getParamSpecsMock.mockReset();
});

describe("useParamSpecs (advanced)", () => {
  const baseOptions = {
    siteId: "plasmodb",
    recordType: "transcript",
    searchName: "GenesByTaxon",
    selectedSearch: null,
    isSearchNameAvailable: true,
    apiRecordTypeValue: "transcript",
    resolveRecordTypeForSearch: () => "transcript",
    enabled: true,
  } as const;

  it("returns the error when the request fails", async () => {
    const apiError = new APIError("validation failed", {
      status: 422,
      statusText: "Unprocessable Entity",
      url: "/api/v1/sites/plasmodb/searches/transcript/GenesByTaxon/param-specs",
      data: null,
    });
    getParamSpecsMock.mockRejectedValueOnce(apiError);

    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(
      () =>
        useParamSpecs({
          ...baseOptions,
          contextValues: {
            organism: {
              type: "multi-pick-vocabulary",
              values: ["Plasmodium falciparum 3D7"],
            },
          },
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(APIError);
    });
    expect(result.current.paramSpecs).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it("returns null error on success", async () => {
    getParamSpecsMock.mockResolvedValueOnce([]);

    const { Wrapper } = createTestWrapper();
    const { result } = renderHook(() => useParamSpecs(baseOptions), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.error).toBeNull();
  });
});
