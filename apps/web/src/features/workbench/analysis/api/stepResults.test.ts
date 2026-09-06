import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock requestJson before importing the module under test
vi.mock("@/lib/api/http", () => ({
  requestJson: vi.fn(),
}));

import {
  getAttributes,
  getRecords,
  getRecordDetail,
  getDistribution,
} from "./stepResults";
import { requestJson } from "@/lib/api/http";

const mockRequestJson = vi.mocked(requestJson);

beforeEach(() => {
  mockRequestJson.mockReset();
});

// ---------------------------------------------------------------------------
// basePath construction (tested indirectly through each function)
// ---------------------------------------------------------------------------

describe("basePath via getAttributes", () => {
  it("uses /experiments/ path for experiment ref", async () => {
    mockRequestJson.mockResolvedValue({ attributes: [], recordType: "gene" });

    await getAttributes({ type: "experiment", id: "exp-123" });

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/exp-123/results/attributes",
    );
  });

  it("uses /gene-sets/ path for gene-set ref", async () => {
    mockRequestJson.mockResolvedValue({ attributes: [], recordType: "gene" });

    await getAttributes({ type: "gene-set", id: "gs-456" });

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs-456/results/attributes",
    );
  });
});

// ---------------------------------------------------------------------------
// getAttributes
// ---------------------------------------------------------------------------

describe("getAttributes", () => {
  it("returns attributes and recordType from API", async () => {
    const mockResponse = {
      attributes: [{ name: "gene_id", displayName: "Gene ID" }],
      recordType: "gene",
    };
    mockRequestJson.mockResolvedValue(mockResponse);

    const result = await getAttributes({ type: "experiment", id: "e1" });

    expect(result).toEqual(mockResponse);
  });

  it("propagates API errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Network error"));

    await expect(getAttributes({ type: "experiment", id: "e1" })).rejects.toThrow(
      "Network error",
    );
  });
});

// ---------------------------------------------------------------------------
// getRecords
// ---------------------------------------------------------------------------

describe("getRecords", () => {
  it("calls with correct path and no query when no opts", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords({ type: "experiment", id: "e1" });

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/records",
      { query: {} },
    );
  });

  it("includes offset and limit in query params", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords({ type: "experiment", id: "e1" }, { offset: 10, limit: 25 });

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/records",
      { query: { offset: "10", limit: "25" } },
    );
  });

  it("includes sort and dir in query params", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords({ type: "gene-set", id: "gs1" }, { sort: "gene_id", dir: "DESC" });

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs1/results/records",
      { query: { sort: "gene_id", dir: "DESC" } },
    );
  });

  it("includes attributes as comma-joined string", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords(
      { type: "experiment", id: "e1" },
      { attributes: ["gene_id", "product", "organism"] },
    );

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/records",
      { query: { attributes: "gene_id,product,organism" } },
    );
  });

  it("includes filter params in query", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords(
      { type: "experiment", id: "e1" },
      { filterAttribute: "organism", filterValue: "P. falciparum" },
    );

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/records",
      {
        query: {
          filterAttribute: "organism",
          filterValue: "P. falciparum",
        },
      },
    );
  });

  it("omits undefined optional params from query", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords({ type: "experiment", id: "e1" }, { offset: 0 });

    const callArgs0 = mockRequestJson.mock.calls[0];
    expect(callArgs0).toBeDefined();
    const query = callArgs0![2]?.query as Record<string, string>;
    expect(query).toEqual({ offset: "0" });
    expect("limit" in query).toBe(false);
    expect("sort" in query).toBe(false);
  });

  it("omits attributes when array is empty", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords({ type: "experiment", id: "e1" }, { attributes: [] });

    const callArgs0 = mockRequestJson.mock.calls[0];
    expect(callArgs0).toBeDefined();
    const query = callArgs0![2]?.query as Record<string, string>;
    expect("attributes" in query).toBe(false);
  });

  it("handles filterValue of empty string", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    // filterValue is "" which is falsy but != null, so it should be included
    await getRecords(
      { type: "experiment", id: "e1" },
      { filterAttribute: "org", filterValue: "" },
    );

    const callArgs0 = mockRequestJson.mock.calls[0];
    expect(callArgs0).toBeDefined();
    const query = callArgs0![2]?.query as Record<string, string>;
    expect(query["filterValue"]).toBe("");
  });

  it("includes all opts simultaneously", async () => {
    mockRequestJson.mockResolvedValue({ records: [], meta: {} });

    await getRecords(
      { type: "gene-set", id: "gs1" },
      {
        offset: 5,
        limit: 50,
        sort: "product",
        dir: "ASC",
        attributes: ["gene_id"],
        filterAttribute: "organism",
        filterValue: "pf3d7",
      },
    );

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs1/results/records",
      {
        query: {
          offset: "5",
          limit: "50",
          sort: "product",
          dir: "ASC",
          attributes: "gene_id",
          filterAttribute: "organism",
          filterValue: "pf3d7",
        },
      },
    );
  });
});

// ---------------------------------------------------------------------------
// getRecordDetail
// ---------------------------------------------------------------------------

describe("getRecordDetail", () => {
  it("sends POST with primaryKey in body", async () => {
    const mockRecord = { gene_id: "PF3D7_0100100", organism: "P. falciparum" };
    mockRequestJson.mockResolvedValue(mockRecord);

    const primaryKey = [{ name: "gene_source_id", value: "PF3D7_0100100" }];
    const result = await getRecordDetail({ type: "experiment", id: "e1" }, primaryKey);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/record",
      {
        method: "POST",
        body: { primaryKey },
      },
    );
    expect(result).toEqual(mockRecord);
  });

  it("works with gene-set entity ref", async () => {
    mockRequestJson.mockResolvedValue({});

    const primaryKey = [{ name: "id", value: "abc" }];
    await getRecordDetail({ type: "gene-set", id: "gs1" }, primaryKey);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs1/results/record",
      {
        method: "POST",
        body: { primaryKey },
      },
    );
  });

  it("handles composite primary key (multiple parts)", async () => {
    mockRequestJson.mockResolvedValue({});

    const primaryKey = [
      { name: "gene_source_id", value: "PF3D7_0100100" },
      { name: "project_id", value: "PlasmoDB" },
    ];
    await getRecordDetail({ type: "experiment", id: "e1" }, primaryKey);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/record",
      {
        method: "POST",
        body: { primaryKey },
      },
    );
  });

  it("propagates API errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("404 Not Found"));

    await expect(
      getRecordDetail({ type: "experiment", id: "e1" }, [
        { name: "id", value: "missing" },
      ]),
    ).rejects.toThrow("404 Not Found");
  });
});

// ---------------------------------------------------------------------------
// getDistribution
// ---------------------------------------------------------------------------

describe("getDistribution", () => {
  it("calls with correct path and URL-encoded attribute name", async () => {
    const mockDist = { bins: [{ label: "A", count: 10 }] };
    mockRequestJson.mockResolvedValue(mockDist);

    const result = await getDistribution(
      { type: "experiment", id: "e1" },
      "gene product",
    );

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/distributions/gene%20product",
    );
    expect(result).toEqual(mockDist);
  });

  it("handles attribute names with special characters", async () => {
    mockRequestJson.mockResolvedValue({});

    await getDistribution({ type: "gene-set", id: "gs1" }, "GO/Function");

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs1/results/distributions/GO%2FFunction",
    );
  });

  it("handles simple attribute names (no encoding needed)", async () => {
    mockRequestJson.mockResolvedValue({});

    await getDistribution({ type: "experiment", id: "e1" }, "organism");

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/experiments/e1/results/distributions/organism",
    );
  });

  it("propagates API errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Server error"));

    await expect(
      getDistribution({ type: "experiment", id: "e1" }, "attr"),
    ).rejects.toThrow("Server error");
  });
});
