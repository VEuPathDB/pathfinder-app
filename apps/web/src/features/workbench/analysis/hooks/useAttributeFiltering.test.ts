/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { createSuspenseWrapper } from "@/lib/query/testing";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";

// ---------------------------------------------------------------------------
// Mock the stepResults API module
// ---------------------------------------------------------------------------

const mockGetAttributes = vi.hoisted(() => vi.fn());

vi.mock("@/features/workbench/analysis/api/stepResults", () => ({
  getAttributes: mockGetAttributes,
  attributesOptions: (entityRef: { type: string; id: string }) => ({
    queryKey: ["experiments", "attributes", entityRef.type, entityRef.id],
    queryFn: () => mockGetAttributes(entityRef),
    staleTime: 60_000,
  }),
}));

// ---------------------------------------------------------------------------
// Mock the attribute filter to pass everything through by default
// ---------------------------------------------------------------------------

const mockIsDistributable = vi.hoisted(() => vi.fn((_a: { name: string }) => true));

vi.mock(
  "@/features/workbench/analysis/components/DistributionExplorer/attributeFilters",
  () => ({
    isDistributableAttr: mockIsDistributable,
  }),
);

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { useAttributeFiltering } from "./useAttributeFiltering";
import type { EntityRef } from "@/features/workbench/analysis/api/stepResults";

function makeAttrs(...names: string[]): RecordAttribute[] {
  return names.map((name) => ({
    name,
    displayName: name.replace(/_/g, " "),
    help: null,
    type: null,
    isDisplayable: true,
    isSortable: false,
    isSuggested: false,
  }));
}

describe("useAttributeFiltering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsDistributable.mockImplementation(() => true);
  });

  it("resets selectedAttr to empty string when entityRef changes", async () => {
    const attrs1 = makeAttrs("organism", "gene_product");
    const attrs2 = makeAttrs("molecular_weight", "go_terms");

    mockGetAttributes
      .mockResolvedValueOnce({ attributes: attrs1, recordType: "gene" })
      .mockResolvedValueOnce({ attributes: attrs2, recordType: "gene" });

    const entity1: EntityRef = { type: "experiment", id: "exp-1" };
    const entity2: EntityRef = { type: "experiment", id: "exp-2" };

    const { Wrapper } = createSuspenseWrapper();
    const { result, rerender } = renderHook(
      ({ entityRef }) => useAttributeFiltering(entityRef),
      { wrapper: Wrapper, initialProps: { entityRef: entity1 } },
    );

    // Wait for first fetch to complete
    await waitFor(() => {
      expect(result.current.selectedAttr).toBe("organism");
    });

    // Switch entity — selectedAttr should reset before new attrs load
    rerender({ entityRef: entity2 });

    // After second fetch completes, auto-selects first distributable attr
    await waitFor(() => {
      expect(result.current.selectedAttr).toBe("molecular_weight");
    });
  });

  it("auto-selects first distributable attribute when attributes load", async () => {
    const attrs = makeAttrs("url_field", "organism", "gene_product");
    // Only organism and gene_product pass the filter
    mockIsDistributable.mockImplementation(
      (a: { name: string }) => a.name !== "url_field",
    );
    mockGetAttributes.mockResolvedValueOnce({
      attributes: attrs,
      recordType: "gene",
    });

    const entity: EntityRef = { type: "experiment", id: "exp-1" };
    const { Wrapper } = createSuspenseWrapper();
    const { result } = renderHook(() => useAttributeFiltering(entity), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.selectedAttr).toBe("organism");
    });

    expect(result.current.attributes).toHaveLength(2);
  });

  it("keeps selectedAttr empty when no distributable attributes exist", async () => {
    mockIsDistributable.mockImplementation(() => false);
    mockGetAttributes.mockResolvedValueOnce({
      attributes: makeAttrs("url_field"),
      recordType: "gene",
    });

    const entity: EntityRef = { type: "experiment", id: "exp-1" };
    const { Wrapper } = createSuspenseWrapper();
    const { result } = renderHook(() => useAttributeFiltering(entity), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.attributes).toHaveLength(0);
    });

    expect(result.current.selectedAttr).toBe("");
  });

  it("allows manual selection via setSelectedAttr", async () => {
    mockGetAttributes.mockResolvedValueOnce({
      attributes: makeAttrs("organism", "gene_product"),
      recordType: "gene",
    });

    const entity: EntityRef = { type: "experiment", id: "exp-1" };
    const { Wrapper } = createSuspenseWrapper();
    const { result } = renderHook(() => useAttributeFiltering(entity), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.selectedAttr).toBe("organism");
    });

    act(() => {
      result.current.setSelectedAttr("gene_product");
    });

    expect(result.current.selectedAttr).toBe("gene_product");
  });
});
