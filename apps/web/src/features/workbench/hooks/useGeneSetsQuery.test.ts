/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { createTestWrapper } from "@/lib/query/testing";
import type { GeneSet } from "@pathfinder/shared";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockListGeneSets = vi.hoisted(() => vi.fn());
const mockGetAuthStatus = vi.hoisted(() => vi.fn());

vi.mock("@/features/workbench/api/geneSets", () => ({
  listGeneSets: mockListGeneSets,
  geneSetsListOptions: (siteId: string) => ({
    queryKey: ["gene-sets", "list", siteId] as const,
    queryFn: () => mockListGeneSets(siteId),
  }),
}));

vi.mock("@/lib/api/veupathdb-auth", () => ({
  authStatusOptions: (siteId: string) => ({
    queryKey: ["auth", "status", siteId] as const,
    queryFn: () => mockGetAuthStatus(siteId),
    enabled: siteId !== "",
  }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeGeneSet(overrides: Partial<GeneSet> & { id: string }): GeneSet {
  return {
    name: "Test gene set",
    siteId: "plasmodb",
    geneIds: ["PF3D7_0100100"],
    source: "strategy",
    geneCount: 1,
    createdAt: "2026-04-06T12:00:00Z",
    stepCount: 1,
    ...overrides,
  };
}

const plasmoSet1 = makeGeneSet({
  id: "gs-1",
  name: "GO:0005634 genes",
  geneIds: ["PF3D7_0100100", "PF3D7_0100200", "PF3D7_0100300"],
  geneCount: 3,
});

const plasmoSet2 = makeGeneSet({
  id: "gs-2",
  name: "Apicoplast membrane",
  geneIds: ["PF3D7_0200100", "PF3D7_0200200"],
  geneCount: 2,
  source: "paste",
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useGeneSetsQuery", () => {
  beforeEach(() => {
    vi.resetModules();
    mockListGeneSets.mockReset();
    mockGetAuthStatus.mockReset();
    mockGetAuthStatus.mockResolvedValue({ signedIn: true, name: "Tester" });
  });

  async function renderGeneSetsQuery(siteId: string) {
    const { useGeneSetsQuery } = await import("./useGeneSetsQuery");
    const { queryClient, Wrapper } = createTestWrapper();
    const hook = renderHook(() => useGeneSetsQuery(siteId), {
      wrapper: Wrapper,
    });
    return { ...hook, queryClient };
  }

  // -------------------------------------------------------------------------
  // 1. Loads gene sets for a siteId
  // -------------------------------------------------------------------------

  it("loads gene sets for siteId", async () => {
    mockListGeneSets.mockResolvedValue([plasmoSet1, plasmoSet2]);

    const { result } = await renderGeneSetsQuery("plasmodb");

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toHaveLength(2);
    expect(result.current.data![0]!.name).toBe("GO:0005634 genes");
    expect(result.current.data![0]!.geneCount).toBe(3);
    expect(result.current.data![1]!.id).toBe("gs-2");
    expect(mockListGeneSets).toHaveBeenCalledWith("plasmodb");
  });

  // -------------------------------------------------------------------------
  // 2. Returns undefined when not authenticated
  // -------------------------------------------------------------------------

  it("returns undefined when not authenticated", async () => {
    mockGetAuthStatus.mockResolvedValue({ signedIn: false, name: null });

    const { result } = await renderGeneSetsQuery("plasmodb");

    await waitFor(() => {
      expect(result.current.fetchStatus).toBe("idle");
    });
    expect(result.current.data).toBeUndefined();
    expect(mockListGeneSets).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 3. Returns undefined when siteId is empty
  // -------------------------------------------------------------------------

  it("returns undefined when siteId is empty", async () => {
    const { result } = await renderGeneSetsQuery("");

    expect(result.current.data).toBeUndefined();
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockListGeneSets).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 4. useInvalidateGeneSets triggers refetch
  // -------------------------------------------------------------------------

  it("useInvalidateGeneSets triggers refetch", async () => {
    const singleSet = [plasmoSet1];
    const twoSets = [plasmoSet1, plasmoSet2];
    mockListGeneSets.mockResolvedValueOnce(singleSet).mockResolvedValueOnce(twoSets);

    const { useGeneSetsQuery } = await import("./useGeneSetsQuery");
    const { useInvalidateGeneSets } = await import("./useInvalidateGeneSets");
    const { Wrapper } = createTestWrapper();

    const { result } = renderHook(
      () => ({
        geneSets: useGeneSetsQuery("plasmodb"),
        invalidate: useInvalidateGeneSets(),
      }),
      { wrapper: Wrapper },
    );

    // Wait for initial fetch (1 gene set)
    await waitFor(() => {
      expect(result.current.geneSets.isSuccess).toBe(true);
    });
    expect(result.current.geneSets.data).toHaveLength(1);

    // Invalidate — triggers second fetch (2 gene sets)
    result.current.invalidate();

    await waitFor(() => {
      expect(result.current.geneSets.data).toHaveLength(2);
    });

    expect(mockListGeneSets).toHaveBeenCalledTimes(2);
  });

  // -------------------------------------------------------------------------
  // 5. Cache is keyed by siteId — no cross-site leakage
  // -------------------------------------------------------------------------

  it("cache is keyed by siteId — no cross-site leakage", async () => {
    mockListGeneSets.mockResolvedValue([plasmoSet1, plasmoSet2]);

    const { queryClient } = await renderGeneSetsQuery("plasmodb");

    // Wait for plasmodb data to land
    await waitFor(() => {
      const data = queryClient.getQueryData(["gene-sets", "list", "plasmodb"]);
      expect(data).toBeDefined();
    });

    // Verify plasmodb cache has 2 sets
    const plasmoData = queryClient.getQueryData<GeneSet[]>([
      "gene-sets",
      "list",
      "plasmodb",
    ]);
    expect(plasmoData).toHaveLength(2);

    // toxodb cache should be empty — different key, never fetched
    const toxoData = queryClient.getQueryData<GeneSet[]>([
      "gene-sets",
      "list",
      "toxodb",
    ]);
    expect(toxoData).toBeUndefined();
  });
});
