/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@pathfinder/shared/generated/hooks/useResolveGenes", () => ({
  resolveGenes: vi.fn(),
}));

vi.mock("../api/geneSets", () => ({
  createGeneSet: vi.fn(),
}));

vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: { selectedSite: string }) => unknown) =>
    selector({ selectedSite: "PlasmoDB" }),
}));

const mockInvalidate = vi.fn().mockResolvedValue(undefined);
vi.mock("@/features/workbench/hooks/useInvalidateGeneSets", () => ({
  useInvalidateGeneSets: () => mockInvalidate,
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

const { resolveGenes } =
  await import("@pathfinder/shared/generated/hooks/useResolveGenes");
const { createGeneSet } = await import("../api/geneSets");
const mockResolve = vi.mocked(resolveGenes);
const mockCreate = vi.mocked(createGeneSet);

import { useGeneSetCreation } from "./useGeneSetCreation";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeGeneSet(overrides: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs-1",
    name: "Test Set",
    siteId: "PlasmoDB",
    geneIds: ["PF3D7_0100100"],
    geneCount: 1,
    source: "paste",
    stepCount: 0,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeResolvedGene(
  geneId: string,
  organism: string = "Plasmodium falciparum 3D7",
) {
  return {
    geneId,
    displayName: geneId,
    organism,
    product: "hypothetical protein",
    geneName: "",
    geneType: "protein_coding",
    location: "chr1:1-100",
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useGeneSetCreation", () => {
  const mockOnCreated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("handleVerify calls resolveGenes and sets resolved/unresolved state", async () => {
    const resolved = makeResolvedGene("PF3D7_0100100");
    mockResolve.mockResolvedValue({
      resolved: [resolved],
      unresolved: ["INVALID_ID"],
    });

    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleVerify(["PF3D7_0100100", "INVALID_ID"]);
    });

    expect(mockResolve).toHaveBeenCalledWith("PlasmoDB", {
      geneIds: ["PF3D7_0100100", "INVALID_ID"],
    });
    await waitFor(() => {
      expect(result.current.verified).toBe(true);
      expect(result.current.resolvedGenes).toEqual([resolved]);
      expect(result.current.unresolvedIds).toEqual(["INVALID_ID"]);
    });
  });

  it("handleVerify does nothing for empty input", async () => {
    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleVerify([]);
    });

    expect(mockResolve).not.toHaveBeenCalled();
    expect(result.current.verified).toBe(false);
  });

  it("handleVerify sets error on failure", async () => {
    mockResolve.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleVerify(["PF3D7_0100100"]);
    });

    await waitFor(() => {
      expect(result.current.error).toBe("Network error");
      expect(result.current.verified).toBe(false);
    });
  });

  it("handleSubmit calls createGeneSet and invalidates query cache", async () => {
    const geneSet = makeGeneSet();
    mockCreate.mockResolvedValue(geneSet);

    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleSubmit("My Set", ["PF3D7_0100100"], "paste");
    });

    expect(mockCreate).toHaveBeenCalledWith({
      name: "My Set",
      source: "paste",
      geneIds: ["PF3D7_0100100"],
      siteId: "PlasmoDB",
    });
    expect(mockInvalidate).toHaveBeenCalled();
    expect(mockOnCreated).toHaveBeenCalled();
  });

  it("handleSubmit uses resolved gene IDs when verified", async () => {
    mockResolve.mockResolvedValue({
      resolved: [makeResolvedGene("PF3D7_0100100", "P. falciparum")],
      unresolved: ["BAD"],
    });
    const geneSet = makeGeneSet();
    mockCreate.mockResolvedValue(geneSet);

    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    // First verify
    await act(async () => {
      await result.current.handleVerify(["PF3D7_0100100", "BAD"]);
    });

    await waitFor(() => {
      expect(result.current.verified).toBe(true);
    });

    // Then submit -- should use only resolved gene IDs
    await act(async () => {
      await result.current.handleSubmit("My Set", ["PF3D7_0100100", "BAD"], "paste");
    });

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        geneIds: ["PF3D7_0100100"],
      }),
    );
  });

  it("handleSubmit shows error for empty name", async () => {
    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleSubmit("", ["PF3D7_0100100"], "paste");
    });

    expect(result.current.error).toBe("Please enter a name for the gene set.");
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("handleSubmit shows error for empty gene IDs", async () => {
    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleSubmit("My Set", [], "paste");
    });

    expect(result.current.error).toBe("No valid gene IDs to add.");
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("handleSubmit sets error on API failure", async () => {
    mockCreate.mockRejectedValue(new Error("Server error"));

    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    await act(async () => {
      await result.current.handleSubmit("My Set", ["G1"], "paste");
    });

    await waitFor(() => {
      expect(result.current.error).toBe("Server error");
      expect(mockOnCreated).not.toHaveBeenCalled();
    });
  });

  it("resetVerification clears verification state", async () => {
    mockResolve.mockResolvedValue({
      resolved: [makeResolvedGene("PF3D7_0100100", "P. falciparum")],
      unresolved: ["BAD"],
    });

    const { result } = renderHook(() =>
      useGeneSetCreation({ onCreated: mockOnCreated }),
    );

    // Verify first
    await act(async () => {
      await result.current.handleVerify(["PF3D7_0100100", "BAD"]);
    });

    await waitFor(() => {
      expect(result.current.verified).toBe(true);
      expect(result.current.resolvedGenes).not.toBeNull();
      expect(result.current.unresolvedIds.length).toBe(1);
    });

    // Reset
    act(() => {
      result.current.resetVerification();
    });

    await waitFor(() => {
      expect(result.current.verified).toBe(false);
      expect(result.current.resolvedGenes).toBeNull();
      expect(result.current.unresolvedIds).toEqual([]);
      expect(result.current.error).toBeNull();
    });
  });
});
