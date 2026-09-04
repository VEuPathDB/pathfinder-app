import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api/http", () => ({
  requestJson: vi.fn(),
}));

import { listControlSets, createControlSet } from "./controlSets";
import { requestJson } from "@/lib/api/http";
import type { ControlSet } from "@pathfinder/shared";

const mockRequestJson = vi.mocked(requestJson);

beforeEach(() => {
  mockRequestJson.mockReset();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const controlSetFixture: ControlSet = {
  id: "cs-1",
  name: "Kinase Controls",
  siteId: "plasmodb",
  recordType: "gene",
  positiveIds: ["PF3D7_0100100", "PF3D7_0200200"],
  negativeIds: ["PF3D7_0300300", "PF3D7_0400400"],
  source: "curation",
  tags: ["kinase", "validated"],
  provenanceNotes: "Manually curated from literature review",
  version: 1,
  isPublic: true,
  userId: "user-1",
  createdAt: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// listControlSets
// ---------------------------------------------------------------------------

describe("listControlSets", () => {
  it("sends GET to /api/v1/control-sets with siteId query", async () => {
    mockRequestJson.mockResolvedValue([controlSetFixture]);

    const result = await listControlSets("plasmodb");

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/control-sets",
      {
        query: { siteId: "plasmodb" },
      },
    );
    expect(result).toEqual([controlSetFixture]);
  });

  it("returns empty array when no control sets exist", async () => {
    mockRequestJson.mockResolvedValue([]);

    const result = await listControlSets("toxodb");

    expect(result).toEqual([]);
  });

  it("returns multiple control sets", async () => {
    const second: ControlSet = {
      ...controlSetFixture,
      id: "cs-2",
      name: "Protease Controls",
    };
    mockRequestJson.mockResolvedValue([controlSetFixture, second]);

    const result = await listControlSets("plasmodb");

    expect(result).toHaveLength(2);
  });

  it("propagates errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Unauthorized"));

    await expect(listControlSets("plasmodb")).rejects.toThrow("Unauthorized");
  });
});

// ---------------------------------------------------------------------------
// createControlSet
// ---------------------------------------------------------------------------

describe("createControlSet", () => {
  it("sends POST to /api/v1/control-sets with required fields", async () => {
    mockRequestJson.mockResolvedValue(controlSetFixture);

    const body = {
      name: "Kinase Controls",
      siteId: "plasmodb",
      recordType: "gene",
      positiveIds: ["PF3D7_0100100", "PF3D7_0200200"],
      negativeIds: ["PF3D7_0300300", "PF3D7_0400400"],
    };

    const result = await createControlSet(body);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/control-sets",
      {
        method: "POST",
        body,
      },
    );
    expect(result).toEqual(controlSetFixture);
  });

  it("includes optional fields when provided", async () => {
    mockRequestJson.mockResolvedValue(controlSetFixture);

    const body = {
      name: "Full Controls",
      siteId: "toxodb",
      recordType: "gene",
      positiveIds: ["G1"],
      negativeIds: ["G2"],
      source: "paper",
      tags: ["paper", "validated"],
      provenanceNotes: "From Smith et al. 2025",
      isPublic: true,
    };

    await createControlSet(body);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/control-sets",
      {
        method: "POST",
        body,
      },
    );
  });

  it("handles empty positive and negative ID lists", async () => {
    mockRequestJson.mockResolvedValue({
      ...controlSetFixture,
      positiveIds: [],
      negativeIds: [],
    });

    const body = {
      name: "Empty Controls",
      siteId: "plasmodb",
      recordType: "gene",
      positiveIds: [] as string[],
      negativeIds: [] as string[],
    };

    await createControlSet(body);

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/control-sets",
      {
        method: "POST",
        body: expect.objectContaining({
          positiveIds: [],
          negativeIds: [],
        }),
      },
    );
  });

  it("propagates errors", async () => {
    mockRequestJson.mockRejectedValue(new Error("Validation error"));

    await expect(
      createControlSet({
        name: "fail",
        siteId: "plasmodb",
        recordType: "gene",
        positiveIds: [],
        negativeIds: [],
      }),
    ).rejects.toThrow("Validation error");
  });
});
