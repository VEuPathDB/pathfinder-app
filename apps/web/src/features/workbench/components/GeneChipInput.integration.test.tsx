// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";

// ---------------------------------------------------------------------------
// Mock stores - must not reference outer variables from vi.mock factories
// ---------------------------------------------------------------------------

const storeState: Record<string, unknown> = {
  geneSets: [] as GeneSet[],
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(storeState),
}));

vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      selectedSite: "PlasmoDB",
    }),
}));

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({
    data: storeState["geneSets"] as GeneSet[],
    isPending: false,
  }),
}));

// ---------------------------------------------------------------------------
// Mock API - only the API layer, sub-components are REAL
// ---------------------------------------------------------------------------

const mockSearchGenes = vi.fn();
const mockResolveGeneIds = vi.fn();

vi.mock("@pathfinder/shared/generated/hooks/useSearchGenes", () => ({
  searchGenes: (...args: unknown[]) => mockSearchGenes(...args),
}));

vi.mock("@pathfinder/shared/generated/hooks/useResolveGenes", () => ({
  resolveGenes: (...args: unknown[]) => mockResolveGeneIds(...args),
}));

// ---------------------------------------------------------------------------
// Import after mocks - all sub-components are real
// ---------------------------------------------------------------------------

import { GeneChipInput } from "./GeneChipInput";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeGeneSet(overrides: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs-1",
    name: "Test Set",
    siteId: "PlasmoDB",
    geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
    geneCount: 2,
    membershipDigest: "0000000000000004",
    source: "strategy",
    stepCount: 1,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("GeneChipInput integration", () => {
  beforeEach(() => {
    storeState["geneSets"] = [];
    mockSearchGenes.mockResolvedValue({ results: [], total: 0 });
    mockResolveGeneIds.mockResolvedValue({ resolved: [], unresolved: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders real GeneChip components with pending status initially", () => {
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100"]}
        onChange={() => {}}
        label="Positive Controls"
        tint="positive"
      />,
    );

    // Real GeneChip renders the gene ID and a data-status attribute
    const chip = screen.getByText("PF3D7_0100100").closest("[data-gene-chip]");
    expect(chip).toBeTruthy();
    expect(chip?.getAttribute("data-status")).toBe("pending");
  });

  it("auto-verifies and updates chip status to verified", async () => {
    mockResolveGeneIds.mockResolvedValue({
      resolved: [
        {
          geneId: "PF3D7_0100100",
          displayName: "PF3D7_0100100",
          organism: "Plasmodium falciparum 3D7",
          product: "erythrocyte membrane protein",
          geneName: "",
          geneType: "protein_coding",
          location: "chr1:1-1000",
        },
      ],
      unresolved: [],
    });

    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100"]}
        onChange={() => {}}
        label="Controls"
      />,
    );

    // After debounce (500ms), resolveGenes fires and chip transitions to verified
    await waitFor(
      () => {
        const chip = screen.getByText("PF3D7_0100100").closest("[data-gene-chip]");
        expect(chip?.getAttribute("data-status")).toBe("verified");
      },
      { timeout: 2000 },
    );
  });

  it("marks invalid genes with invalid status", async () => {
    mockResolveGeneIds.mockResolvedValue({
      resolved: [],
      unresolved: ["FAKE_GENE"],
    });

    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["FAKE_GENE"]}
        onChange={() => {}}
        label="Controls"
      />,
    );

    await waitFor(
      () => {
        const chip = screen.getByText("FAKE_GENE").closest("[data-gene-chip]");
        expect(chip?.getAttribute("data-status")).toBe("invalid");
      },
      { timeout: 2000 },
    );
  });

  it("autocomplete search -> select -> calls onChange with new gene", async () => {
    mockSearchGenes.mockResolvedValue({
      results: [
        {
          geneId: "PF3D7_0300300",
          displayName: "PF3D7_0300300",
          organism: "Plasmodium falciparum 3D7",
          product: "some product",
        },
      ],
      total: 1,
    });

    const onChange = vi.fn();
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={onChange}
        label="Controls"
      />,
    );

    // Type in the real GeneAutocomplete input
    const input = screen.getByPlaceholderText("Search genes...");
    act(() => {
      fireEvent.change(input, { target: { value: "PF3D7" } });
    });

    // Wait for debounced search (300ms) to return results
    await waitFor(
      () => {
        expect(screen.getByText("PF3D7_0300300")).toBeTruthy();
      },
      { timeout: 1000 },
    );

    // Click the autocomplete result
    fireEvent.click(screen.getByText("PF3D7_0300300"));

    expect(onChange).toHaveBeenCalledWith(["PF3D7_0300300"]);
  });

  it("chip removal calls onChange without the removed gene", () => {
    const onChange = vi.fn();
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100", "PF3D7_0200200"]}
        onChange={onChange}
        label="Controls"
      />,
    );

    // Real GeneChip renders a remove button with aria-label
    fireEvent.click(screen.getByRole("button", { name: "Remove PF3D7_0100100" }));
    expect(onChange).toHaveBeenCalledWith(["PF3D7_0200200"]);
  });

  it("GeneSetPicker adds genes from a gene set", () => {
    storeState["geneSets"] = [makeGeneSet()];

    const onChange = vi.fn();
    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={onChange}
        label="Controls"
      />,
    );

    // Real GeneSetPicker renders "From Gene Set" button
    fireEvent.click(screen.getByText("From Gene Set"));

    // Dropdown appears with the gene set
    expect(screen.getByText("Test Set")).toBeTruthy();

    // Click the gene set
    fireEvent.click(screen.getByText("Test Set"));

    expect(onChange).toHaveBeenCalledWith(["PF3D7_0100100", "PF3D7_0200200"]);
  });

  it("applies positive tint styling", () => {
    const { container } = render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={() => {}}
        label="Positive Controls"
        tint="positive"
      />,
    );

    const wrapper = container.firstElementChild;
    expect(wrapper?.className).toContain("border-l-success");
  });

  it("applies negative tint styling", () => {
    const { container } = render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={[]}
        onChange={() => {}}
        label="Negative Controls"
        tint="negative"
      />,
    );

    const wrapper = container.firstElementChild;
    expect(wrapper?.className).toContain("border-l-warning");
  });

  it("mixed verification: some verified, some invalid", async () => {
    mockResolveGeneIds.mockResolvedValue({
      resolved: [
        {
          geneId: "PF3D7_0100100",
          displayName: "PF3D7_0100100",
          organism: "Plasmodium falciparum 3D7",
          product: "real gene",
          geneName: "",
          geneType: "",
          location: "",
        },
      ],
      unresolved: ["NOT_A_GENE"],
    });

    render(
      <GeneChipInput
        siteId="PlasmoDB"
        value={["PF3D7_0100100", "NOT_A_GENE"]}
        onChange={() => {}}
        label="Controls"
      />,
    );

    await waitFor(
      () => {
        const verifiedChip = screen
          .getByText("PF3D7_0100100")
          .closest("[data-gene-chip]");
        const invalidChip = screen.getByText("NOT_A_GENE").closest("[data-gene-chip]");
        expect(verifiedChip?.getAttribute("data-status")).toBe("verified");
        expect(invalidChip?.getAttribute("data-status")).toBe("invalid");
      },
      { timeout: 2000 },
    );
  });
});
