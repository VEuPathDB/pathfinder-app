// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { GeneSet } from "@pathfinder/shared";

// ---------------------------------------------------------------------------
// Mock the workbench store so AnalysisPanelContainer renders children
// ---------------------------------------------------------------------------

function makeGeneSet(id: string, geneIds: string[], siteId = "PlasmoDB"): GeneSet {
  return {
    id,
    name: `Set ${id}`,
    siteId,
    geneIds,
    source: "paste",
    geneCount: geneIds.length,
    membershipDigest: "000000000000000f",
    createdAt: "2026-03-09T00:00:00Z",
    stepCount: 1,
    parentSetIds: [],
  };
}

const storeState: Record<string, unknown> = {
  geneSets: [] as GeneSet[],
  selectedSetIds: [] as string[],
  expandedPanels: new Set(["ensemble"]),
  togglePanel: vi.fn(),
  toggleSetSelection: vi.fn(),
};

const mockStore = (selector: (s: Record<string, unknown>) => unknown) =>
  selector(storeState);

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    mockStore(selector),
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

// Mock the API call
const mockRequestJson = vi.fn();
vi.mock("@/lib/api/http", () => ({
  requestJson: (...args: unknown[]) => mockRequestJson(...args),
}));

// Mock GeneChipInput's dependencies
vi.mock("@pathfinder/shared/generated/hooks/useResolveGenes", () => ({
  resolveGenes: vi.fn().mockResolvedValue({ resolved: [], unresolved: [] }),
}));

vi.mock("@pathfinder/shared/generated/hooks/useSearchGenes", () => ({
  searchGenes: vi.fn().mockResolvedValue([]),
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { EnsemblePanel } from "./EnsemblePanel";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EnsemblePanel", () => {
  afterEach(() => {
    cleanup();
    mockRequestJson.mockReset();
  });

  beforeEach(() => {
    storeState["geneSets"] = [];
    storeState["selectedSetIds"] = [];
    storeState["expandedPanels"] = new Set(["ensemble"]);
  });

  it("shows disabled state when fewer than 2 gene sets exist", () => {
    storeState["geneSets"] = [makeGeneSet("s1", ["G1"])];
    render(<EnsemblePanel />);
    expect(screen.getByText("Ensemble Scoring")).toBeTruthy();
    // Panel header shows but content should not render (disabled)
    expect(screen.queryByText("Compute")).toBeNull();
  });

  it("renders gene set selector when 2+ gene sets exist", () => {
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1", "G2"]),
      makeGeneSet("s2", ["G2", "G3"]),
    ];
    storeState["selectedSetIds"] = ["s1", "s2"];

    render(<EnsemblePanel />);
    expect(screen.getByText("Set s1")).toBeTruthy();
    expect(screen.getByText("Set s2")).toBeTruthy();
  });

  it("disables compute button when fewer than 2 sets are selected", () => {
    storeState["geneSets"] = [makeGeneSet("s1", ["G1"]), makeGeneSet("s2", ["G2"])];
    storeState["selectedSetIds"] = ["s1"];

    render(<EnsemblePanel />);
    const button = screen.getByRole("button", { name: /compute/i });
    expect(button).toBeTruthy();
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows ranked table after computation", async () => {
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1", "G2"]),
      makeGeneSet("s2", ["G2", "G3"]),
    ];
    storeState["selectedSetIds"] = ["s1", "s2"];

    mockRequestJson.mockResolvedValueOnce([
      { geneId: "G2", frequency: 1.0, count: 2, total: 2, inPositives: false },
      { geneId: "G1", frequency: 0.5, count: 1, total: 2, inPositives: false },
      { geneId: "G3", frequency: 0.5, count: 1, total: 2, inPositives: false },
    ]);

    render(<EnsemblePanel />);
    const button = screen.getByRole("button", { name: /compute/i });
    fireEvent.click(button);

    // Each gene's row shows its real ensemble frequency: G2 in both sets
    // (2/2 = 100.0%), G1 and G3 each in one (1/2 = 50.0%).
    const g2Row = (await screen.findByText("G2")).closest("tr");
    expect(g2Row).toHaveTextContent("100.0%");
    expect(screen.getByText("G1").closest("tr")).toHaveTextContent("50.0%");
    expect(screen.getByText("G3").closest("tr")).toHaveTextContent("50.0%");
  });

  it("marks a gene present in the positives with the success token", async () => {
    storeState["geneSets"] = [makeGeneSet("s1", ["G1"]), makeGeneSet("s2", ["G1"])];
    storeState["selectedSetIds"] = ["s1", "s2"];

    mockRequestJson.mockResolvedValueOnce([
      { geneId: "G1", frequency: 1.0, count: 2, total: 2, inPositives: true },
    ]);

    render(<EnsemblePanel />);
    fireEvent.click(screen.getByRole("button", { name: /compute/i }));

    const yes = await screen.findByText("Yes");
    expect(yes).toHaveClass("text-success");
    expect(yes.className).not.toContain("green-");
    expect(yes.className).not.toContain("dark:");
  });

  it("sends correct request body to the API", async () => {
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1"]),
      makeGeneSet("s2", ["G2"]),
      makeGeneSet("s3", ["G3"]),
    ];
    storeState["selectedSetIds"] = ["s1", "s3"];

    mockRequestJson.mockResolvedValueOnce([]);

    render(<EnsemblePanel />);
    fireEvent.click(screen.getByRole("button", { name: /compute/i }));

    expect(mockRequestJson).toHaveBeenCalledWith(
      expect.anything(),
      "/api/v1/gene-sets/ensemble",
      {
        method: "POST",
        body: { geneSetIds: ["s1", "s3"], positiveControls: null },
      },
    );
  });

  // -----------------------------------------------------------------------
  // Cross-site validation tests
  // -----------------------------------------------------------------------

  it("shows error when selected gene sets are from different sites", async () => {
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1", "G2"], "PlasmoDB"),
      makeGeneSet("s2", ["G2", "G3"], "ToxoDB"),
    ];
    storeState["selectedSetIds"] = ["s1", "s2"];

    render(<EnsemblePanel />);
    const button = screen.getByRole("button", { name: /compute/i });
    fireEvent.click(button);

    // Should show cross-site error, not call the API
    await waitFor(() => {
      expect(screen.getByText(/different sites/i)).toBeTruthy();
    });
    expect(mockRequestJson).not.toHaveBeenCalled();
  });

  it("shows no error when all gene sets are from the same site", async () => {
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1", "G2"], "PlasmoDB"),
      makeGeneSet("s2", ["G2", "G3"], "PlasmoDB"),
      makeGeneSet("s3", ["G3", "G4"], "PlasmoDB"),
    ];
    storeState["selectedSetIds"] = ["s1", "s2", "s3"];

    mockRequestJson.mockResolvedValueOnce([
      { geneId: "G2", frequency: 0.67, count: 2, total: 3, inPositives: false },
    ]);

    render(<EnsemblePanel />);
    fireEvent.click(screen.getByRole("button", { name: /compute/i }));

    // Should call the API (no cross-site error)
    expect(mockRequestJson).toHaveBeenCalled();

    // Wait for results - no error text about different sites
    await screen.findByText("G2");
    expect(screen.queryByText(/different sites/i)).toBeNull();
  });

  it("clears cross-site error when computation succeeds", async () => {
    // First: trigger the cross-site error
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1"], "PlasmoDB"),
      makeGeneSet("s2", ["G2"], "ToxoDB"),
    ];
    storeState["selectedSetIds"] = ["s1", "s2"];

    const { rerender } = render(<EnsemblePanel />);
    fireEvent.click(screen.getByRole("button", { name: /compute/i }));

    await waitFor(() => {
      expect(screen.getByText(/different sites/i)).toBeTruthy();
    });

    // Now fix the selection: both from same site
    storeState["geneSets"] = [
      makeGeneSet("s1", ["G1"], "PlasmoDB"),
      makeGeneSet("s2", ["G2"], "PlasmoDB"),
    ];
    storeState["selectedSetIds"] = ["s1", "s2"];

    mockRequestJson.mockResolvedValueOnce([
      { geneId: "G1", frequency: 0.5, count: 1, total: 2, inPositives: false },
    ]);

    rerender(<EnsemblePanel />);
    fireEvent.click(screen.getByRole("button", { name: /compute/i }));

    // Error should be cleared once computation succeeds
    await waitFor(() => {
      expect(screen.queryByText(/different sites/i)).toBeNull();
    });
  });
});
