// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { Experiment } from "@pathfinder/shared";
import { geneConfidenceRequestSchema } from "@pathfinder/shared/generated/zod/geneConfidenceRequestSchema";

// ---------------------------------------------------------------------------
// Mock the workbench store so AnalysisPanelContainer renders children
// ---------------------------------------------------------------------------

const storeState: Record<string, unknown> = {
  activeSetId: "set-1",
  lastExperiment: null as Experiment | null,
  lastExperimentSetId: null as string | null,
  expandedPanels: new Set(["confidence"]),
  togglePanel: vi.fn(),
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(storeState),
}));

// Mock the API call
const mockRequestJson = vi.fn();
vi.mock("@/lib/api/http", () => ({
  requestJson: (...args: unknown[]) => mockRequestJson(...args),
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { ConfidencePanel } from "./ConfidencePanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeExperiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: "exp-1",
    config: {
      siteId: "PlasmoDB",
      recordType: "gene",
      searchName: "GenesByTaxon",
      parameters: {},
      positiveControls: ["PF3D7_0100100"],
      negativeControls: [],
      controlsSearchName: "GeneByLocusTag",
      controlsParamName: "ds_gene_ids",
      controlsValueFormat: "newline",
      enableCrossValidation: false,
      kFolds: 5,
      enrichmentTypes: [],
      name: "Test",
      description: "",
      mode: "single",
    },
    status: "completed",
    metrics: null,
    enrichmentResults: [],
    crossValidation: null,
    truePositiveGenes: [],
    falsePositiveGenes: [],
    trueNegativeGenes: [],
    falseNegativeGenes: [],
    notes: null,
    batchId: null,
    benchmarkId: null,
    controlSetLabel: null,
    isPrimaryBenchmark: false,
    error: null,
    totalTimeSeconds: null,
    createdAt: "2026-03-09T00:00:00Z",
    completedAt: "2026-03-09T00:01:00Z",
    wdkStrategyId: null,
    wdkStepId: null,
    robustness: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ConfidencePanel", () => {
  afterEach(() => {
    cleanup();
    mockRequestJson.mockReset();
  });

  beforeEach(() => {
    storeState["activeSetId"] = "set-1";
    storeState["lastExperiment"] = null;
    storeState["lastExperimentSetId"] = null;
    storeState["expandedPanels"] = new Set(["confidence"]);
  });

  it("shows disabled state when no experiment is available", () => {
    render(<ConfidencePanel />);
    expect(screen.getByText("Gene Confidence")).toBeTruthy();
    // No table content when disabled
    expect(screen.queryByRole("table")).toBeNull();
    expect(mockRequestJson).not.toHaveBeenCalled();
  });

  it("shows disabled state when experiment has no classified genes", () => {
    storeState["lastExperiment"] = makeExperiment();
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(mockRequestJson).not.toHaveBeenCalled();
  });

  it("calls the backend API and renders scores", async () => {
    mockRequestJson.mockResolvedValueOnce([
      {
        geneId: "G1",
        compositeScore: 0.333,
        classificationScore: 1.0,
        ensembleScore: 0.0,
        enrichmentScore: 0.0,
      },
      {
        geneId: "G2",
        compositeScore: -0.333,
        classificationScore: -1.0,
        ensembleScore: 0.0,
        enrichmentScore: 0.0,
      },
    ]);

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1", name: "Gene1" }],
      falsePositiveGenes: [{ id: "G2", name: "Gene2" }],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeTruthy();
    });

    // Each row renders its real scores: composite .toFixed(3), classification
    // .toFixed(1) — G1 a confident TP (+1 → 0.333), G2 an FP (-1 → -0.333).
    const g1Row = screen.getByText("G1").closest("tr");
    expect(g1Row).toHaveTextContent("0.333");
    expect(g1Row).toHaveTextContent("1.0");
    const g2Row = screen.getByText("G2").closest("tr");
    expect(g2Row).toHaveTextContent("-0.333");
    expect(g2Row).toHaveTextContent("-1.0");
  });

  it("colors a positive score with success and a negative score with destructive", async () => {
    mockRequestJson.mockResolvedValueOnce([
      {
        geneId: "G1",
        compositeScore: 0.333,
        classificationScore: 1.0,
        ensembleScore: 0.0,
        enrichmentScore: 0.0,
      },
      {
        geneId: "G2",
        compositeScore: -0.333,
        classificationScore: -1.0,
        ensembleScore: 0.0,
        enrichmentScore: 0.0,
      },
    ]);

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1", name: "Gene1" }],
      falsePositiveGenes: [{ id: "G2", name: "Gene2" }],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeTruthy();
    });

    expect(screen.getByText("0.333")).toHaveClass("text-success");
    expect(screen.getByText("-0.333")).toHaveClass("text-destructive");
    const table = screen.getByRole("table");
    expect(table.innerHTML).not.toContain("green-");
    expect(table.innerHTML).not.toContain("dark:text-");
  });

  it("sends correct request body with gene IDs", async () => {
    mockRequestJson.mockResolvedValueOnce([]);

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
      falsePositiveGenes: [{ id: "G2" }],
      falseNegativeGenes: [{ id: "G3" }],
      trueNegativeGenes: [{ id: "G4" }],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(mockRequestJson).toHaveBeenCalled();
    });

    const [, url, opts] = mockRequestJson.mock.calls[0] as [
      unknown,
      string,
      { method: string; body: Record<string, unknown> },
    ];
    expect(url).toBe("/api/v1/gene-sets/confidence");
    expect(opts.method).toBe("POST");
    expect(opts.body).toMatchObject({
      tpIds: ["G1"],
      fpIds: ["G2"],
      fnIds: ["G3"],
      tnIds: ["G4"],
    });
  });

  it("sends enrichment gene counts derived from enrichment results", async () => {
    mockRequestJson.mockResolvedValueOnce([]);

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
      enrichmentResults: [
        {
          analysisType: "go_process",
          totalGenesAnalyzed: 10,
          backgroundSize: 100,
          terms: [
            {
              termId: "GO:0001",
              termName: "process1",
              geneCount: 1,
              backgroundCount: 10,
              foldEnrichment: 10,
              oddsRatio: 5,
              pValue: 0.001,
              fdr: 0.01,
              bonferroni: 0.05,
              genes: ["G1"],
            },
            {
              termId: "GO:0002",
              termName: "process2",
              geneCount: 1,
              backgroundCount: 10,
              foldEnrichment: 10,
              oddsRatio: 5,
              pValue: 0.001,
              fdr: 0.01,
              bonferroni: 0.05,
              genes: ["G1", "OTHER"],
            },
            {
              termId: "GO:0003",
              termName: "insignificant",
              geneCount: 1,
              backgroundCount: 10,
              foldEnrichment: 1,
              oddsRatio: 1,
              pValue: 0.5,
              fdr: 0.8,
              bonferroni: 1.0,
              genes: ["G1"],
            },
          ],
        },
      ],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(mockRequestJson).toHaveBeenCalled();
    });

    const body = (
      mockRequestJson.mock.calls[0] as [
        unknown,
        string,
        { body: Record<string, unknown> },
      ]
    )[2].body;

    // G1 appears in 2 significant terms (FDR ≤ 0.05), OTHER in 1
    expect(body["enrichmentGeneCounts"]).toEqual({ G1: 2, OTHER: 1 });
    // 2 significant terms total
    expect(body["maxEnrichmentTerms"]).toBe(2);
  });

  it("sends a body the API contract accepts when no enrichment term is significant", async () => {
    mockRequestJson.mockResolvedValueOnce([]);

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
      enrichmentResults: [],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(mockRequestJson).toHaveBeenCalled();
    });

    const body = (
      mockRequestJson.mock.calls[0] as [
        unknown,
        string,
        { body: Record<string, unknown> },
      ]
    )[2].body;

    const parsed = geneConfidenceRequestSchema.safeParse(body);
    expect(parsed.error?.issues ?? []).toEqual([]);
  });

  it("renders all four score columns including Ensemble", async () => {
    mockRequestJson.mockResolvedValueOnce([
      {
        geneId: "G1",
        compositeScore: 0.5,
        classificationScore: 1.0,
        ensembleScore: 0.5,
        enrichmentScore: 0.0,
      },
    ]);

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeTruthy();
    });

    // All four column headers
    expect(screen.getByText("Composite")).toBeTruthy();
    expect(screen.getByText("Classification")).toBeTruthy();
    expect(screen.getByText("Ensemble")).toBeTruthy();
    expect(screen.getByText("Enrichment")).toBeTruthy();
  });

  it("shows disabled when experiment belongs to a different set", () => {
    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
    });
    storeState["lastExperimentSetId"] = "set-other";

    render(<ConfidencePanel />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(mockRequestJson).not.toHaveBeenCalled();
  });

  it("shows loading state while API call is in progress", async () => {
    // Never resolve the promise — keeps loading
    mockRequestJson.mockReturnValueOnce(new Promise(() => {}));

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(screen.getByText("Computing scores...")).toBeTruthy();
    });
  });

  it("shows error message when API call fails", async () => {
    mockRequestJson.mockRejectedValueOnce(new Error("Network failure"));

    storeState["lastExperiment"] = makeExperiment({
      truePositiveGenes: [{ id: "G1" }],
    });
    storeState["lastExperimentSetId"] = "set-1";

    render(<ConfidencePanel />);

    await waitFor(() => {
      expect(screen.getByText("Network failure")).toBeTruthy();
    });
  });
});
