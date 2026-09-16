import { describe, expect, it, vi, beforeEach } from "vitest";

// Mock requestJson and requestVoid before importing the module under test
vi.mock("@/lib/api/http", () => ({
  requestJson: vi.fn(),
  requestVoid: vi.fn(),
}));

import {
  createGeneSet,
  listGeneSets,
  deleteGeneSet,
  performSetOperation,
  enrichGeneSet,
  createGeneSetFromStrategy,
} from "./geneSets";
import type { CreateFromStrategyArgs } from "./geneSets";
import type { CreateGeneSetRequest } from "@pathfinder/shared/generated/types/CreateGeneSetRequest";
import type { SetOperationRequest } from "@pathfinder/shared/generated/types/SetOperationRequest";
import { requestJson, requestVoid } from "@/lib/api/http";
import type { EnrichmentResult, GeneSet } from "@pathfinder/shared";

const mockRequestJson = vi.mocked(requestJson);
const mockRequestVoid = vi.mocked(requestVoid);

beforeEach(() => {
  mockRequestJson.mockReset();
  mockRequestVoid.mockReset();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const geneSetFixture: GeneSet = {
  id: "gs-1",
  name: "My Gene Set",
  siteId: "plasmodb",
  geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
  geneCount: 2,
  membershipDigest: "000000000000000f",
  source: "paste",
  stepCount: 1,
  createdAt: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// createGeneSet
// ---------------------------------------------------------------------------

describe("createGeneSet", () => {
  it("sends POST to /api/v1/gene-sets with the request body", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const req: CreateGeneSetRequest = {
      name: "My Gene Set",
      source: "paste",
      geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
      siteId: "plasmodb",
    };

    const result = await createGeneSet(req);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets",
      {
        method: "POST",
        body: req,
      },
    );
    expect(result).toEqual(geneSetFixture);
  });

  it("includes optional fields when provided", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const req: CreateGeneSetRequest = {
      name: "Strategy Set",
      source: "strategy",
      geneIds: ["G1"],
      siteId: "toxodb",
      wdkStrategyId: 42,
      wdkStepId: 7,
      searchName: "GeneByTextSearch",
      recordType: "gene",
      parameters: { text_expression: { type: "string", value: "kinase" } },
    };

    await createGeneSet(req);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets",
      {
        method: "POST",
        body: req,
      },
    );
  });

  it("propagates API errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("500 Internal Server Error"));

    await expect(
      createGeneSet({
        name: "fail",
        source: "paste",
        geneIds: [],
        siteId: "plasmodb",
      }),
    ).rejects.toThrow("500 Internal Server Error");
  });
});

// ---------------------------------------------------------------------------
// listGeneSets
// ---------------------------------------------------------------------------

describe("listGeneSets", () => {
  it("sends GET to /api/v1/gene-sets without query when no siteId", async () => {
    mockRequestJson.mockResolvedValue([geneSetFixture]);

    const result = await listGeneSets();

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets",
      {},
    );
    expect(result).toEqual([geneSetFixture]);
  });

  it("includes siteId in query when provided", async () => {
    mockRequestJson.mockResolvedValue([]);

    await listGeneSets("plasmodb");

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets",
      {
        query: { siteId: "plasmodb" },
      },
    );
  });

  it("returns empty array when no gene sets exist", async () => {
    mockRequestJson.mockResolvedValue([]);

    const result = await listGeneSets("toxodb");

    expect(result).toEqual([]);
  });

  it("propagates errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Network error"));

    await expect(listGeneSets()).rejects.toThrow("Network error");
  });
});

// ---------------------------------------------------------------------------
// deleteGeneSet
// ---------------------------------------------------------------------------

describe("deleteGeneSet", () => {
  it("sends DELETE to /api/v1/gene-sets/:id", async () => {
    mockRequestVoid.mockResolvedValue(undefined);

    await deleteGeneSet("gs-1");

    expect(mockRequestVoid).toHaveBeenCalledWith("/api/v1/gene-sets/gs-1", {
      method: "DELETE",
    });
  });

  it("encodes special characters in the ID", async () => {
    mockRequestVoid.mockResolvedValue(undefined);

    await deleteGeneSet("gs/special");

    expect(mockRequestVoid).toHaveBeenCalledWith("/api/v1/gene-sets/gs/special", {
      method: "DELETE",
    });
  });

  it("propagates errors on deletion failure", async () => {
    mockRequestVoid.mockRejectedValue(new Error("404 Not Found"));

    await expect(deleteGeneSet("nonexistent")).rejects.toThrow("404 Not Found");
  });
});

// ---------------------------------------------------------------------------
// performSetOperation
// ---------------------------------------------------------------------------

describe("performSetOperation", () => {
  it("sends POST to /api/v1/gene-sets/operations", async () => {
    const resultSet: GeneSet = {
      ...geneSetFixture,
      id: "gs-derived",
      name: "Intersection",
      source: "derived",
    };
    mockRequestJson.mockResolvedValue(resultSet);

    const req: SetOperationRequest = {
      operation: "intersect",
      setAId: "gs-1",
      setBId: "gs-2",
      name: "Intersection",
    };

    const result = await performSetOperation(req);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/operations",
      {
        method: "POST",
        body: req,
      },
    );
    expect(result).toEqual(resultSet);
  });

  it("supports union operation", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const req: SetOperationRequest = {
      operation: "union",
      setAId: "gs-1",
      setBId: "gs-2",
      name: "Union",
    };

    await performSetOperation(req);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/operations",
      {
        method: "POST",
        body: expect.objectContaining({ operation: "union" }),
      },
    );
  });

  it("supports minus operation", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const req: SetOperationRequest = {
      operation: "minus",
      setAId: "gs-1",
      setBId: "gs-2",
      name: "Difference",
    };

    await performSetOperation(req);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/operations",
      {
        method: "POST",
        body: expect.objectContaining({ operation: "minus" }),
      },
    );
  });

  it("propagates errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Validation error"));

    await expect(
      performSetOperation({
        operation: "intersect",
        setAId: "gs-1",
        setBId: "gs-2",
        name: "fail",
      }),
    ).rejects.toThrow("Validation error");
  });
});

// ---------------------------------------------------------------------------
// enrichGeneSet
// ---------------------------------------------------------------------------

describe("enrichGeneSet", () => {
  it("sends POST to /api/v1/gene-sets/:id/enrich with enrichment types", async () => {
    const enrichmentResults: EnrichmentResult[] = [
      {
        analysisType: "go_function",
        terms: [],
        totalGenesAnalyzed: 10,
        backgroundSize: 5000,
      },
    ];
    mockRequestJson.mockResolvedValue(enrichmentResults);

    const result = await enrichGeneSet("gs-1", ["go_function", "pathway"]);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs-1/enrich",
      {
        method: "POST",
        body: { enrichmentTypes: ["go_function", "pathway"] },
      },
    );
    expect(result).toEqual(enrichmentResults);
  });

  it("handles empty enrichment types array", async () => {
    mockRequestJson.mockResolvedValue([]);

    await enrichGeneSet("gs-1", []);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/gs-1/enrich",
      {
        method: "POST",
        body: { enrichmentTypes: [] },
      },
    );
  });

  it("propagates errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Enrichment failed"));

    await expect(enrichGeneSet("gs-1", ["go_function"])).rejects.toThrow(
      "Enrichment failed",
    );
  });
});

// ---------------------------------------------------------------------------
// createGeneSetFromStrategy
// ---------------------------------------------------------------------------

describe("createGeneSetFromStrategy", () => {
  it("calls createGeneSet with strategy source and mapped fields", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const args: CreateFromStrategyArgs = {
      name: "From Strategy",
      siteId: "plasmodb",
      wdkStrategyId: 42,
      wdkStepId: 7,
      searchName: "GeneByTextSearch",
      recordType: "gene",
      parameters: { text_expression: { type: "string", value: "kinase" } },
      geneIds: ["G1", "G2"],
    };

    await createGeneSetFromStrategy(args);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets",
      {
        method: "POST",
        body: {
          name: "From Strategy",
          source: "strategy",
          geneIds: ["G1", "G2"],
          siteId: "plasmodb",
          wdkStrategyId: 42,
          wdkStepId: 7,
          searchName: "GeneByTextSearch",
          recordType: "gene",
          parameters: { text_expression: { type: "string", value: "kinase" } },
        },
      },
    );
  });

  it("defaults geneIds to empty array when not provided", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const args: CreateFromStrategyArgs = {
      name: "Empty Set",
      siteId: "toxodb",
      wdkStrategyId: 99,
    };

    await createGeneSetFromStrategy(args);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets",
      {
        method: "POST",
        body: expect.objectContaining({
          geneIds: [],
          source: "strategy",
        }),
      },
    );
  });

  it("passes optional fields as undefined when not provided", async () => {
    mockRequestJson.mockResolvedValue(geneSetFixture);

    const args: CreateFromStrategyArgs = {
      name: "Minimal",
      siteId: "plasmodb",
      wdkStrategyId: 1,
    };

    await createGeneSetFromStrategy(args);

    const body = mockRequestJson.mock.calls[0]![2] as { body: CreateGeneSetRequest };
    expect(body.body).toEqual({
      name: "Minimal",
      source: "strategy",
      geneIds: [],
      siteId: "plasmodb",
      wdkStrategyId: 1,
    });
  });

  it("propagates errors from createGeneSet", async () => {
    mockRequestJson.mockRejectedValue(new Error("Creation failed"));

    await expect(
      createGeneSetFromStrategy({
        name: "fail",
        siteId: "plasmodb",
        wdkStrategyId: 1,
      }),
    ).rejects.toThrow("Creation failed");
  });
});
