// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { Experiment } from "@pathfinder/shared";
import { createTestWrapper } from "@/lib/query/testing";

const mockListGeneSetExperiments = vi.hoisted(() => vi.fn());

vi.mock("@/features/workbench/api/experiments", () => ({
  listGeneSetExperiments: mockListGeneSetExperiments,
  geneSetExperimentsOptions: (geneSetId: string) => ({
    queryKey: ["experiments", "by-gene-set", geneSetId] as const,
    queryFn: () => mockListGeneSetExperiments(geneSetId),
    enabled: geneSetId !== "",
  }),
}));

const storeState: Record<string, unknown> = {
  activeSetId: "gs-gametocyte",
  lastExperiment: null as Experiment | null,
  lastExperimentSetId: null as string | null,
  expandedPanels: new Set<string>(),
  togglePanel: vi.fn(),
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(storeState),
}));

import { CustomEnrichmentPanel } from "./CustomEnrichmentPanel";
import { SweepPanel } from "./SweepPanel";

const GAMETOCYTE = "gs-gametocyte";
const MEROZOITE = "gs-merozoite";

function evaluationOf(geneSetId: string, id: string): Experiment {
  return {
    id,
    config: {
      siteId: "plasmodb",
      recordType: "gene",
      searchName: "GenesByTaxon",
      parameters: {},
      positiveControls: ["PF3D7_0304600"],
      negativeControls: ["PF3D7_0930300"],
      controlsSearchName: "GeneByLocusTag",
      controlsParamName: "ds_gene_ids",
      controlsValueFormat: "newline",
      enableCrossValidation: false,
      kFolds: 5,
      enrichmentTypes: [],
      name: "gametocyte secreted (evaluation)",
      description: "",
      mode: "single",
      geneSetId,
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
    createdAt: "2026-09-15T10:00:00Z",
    completedAt: "2026-09-15T10:01:00Z",
    wdkStrategyId: null,
    wdkStepId: null,
    robustness: null,
  };
}

function renderPanels(): { rerender: () => void } {
  const { Wrapper } = createTestWrapper();
  const tree = () => (
    <Wrapper>
      <SweepPanel />
      <CustomEnrichmentPanel />
    </Wrapper>
  );
  const view = render(tree());
  return { rerender: () => view.rerender(tree()) };
}

function sweepHeader(): HTMLButtonElement {
  return screen.getByRole("button", { name: /Parameter Sweep/ });
}

function enrichmentHeader(): HTMLButtonElement {
  return screen.getByRole("button", { name: /Custom Enrichment/ });
}

describe("the panels a completed evaluation unlocks", () => {
  beforeEach(() => {
    mockListGeneSetExperiments.mockReset();
    storeState["activeSetId"] = GAMETOCYTE;
    storeState["lastExperiment"] = null;
    storeState["lastExperimentSetId"] = null;
    storeState["expandedPanels"] = new Set<string>();
  });

  afterEach(() => {
    cleanup();
  });

  it("enables Sweep and Custom Enrichment when the active set holds an evaluation", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      evaluationOf(GAMETOCYTE, "exp-gametocyte"),
    ]);

    renderPanels();

    await waitFor(() => {
      expect(sweepHeader().disabled).toBe(false);
    });
    expect(enrichmentHeader().disabled).toBe(false);
  });

  it("keeps both locked when the only evaluation belongs to another set", async () => {
    mockListGeneSetExperiments.mockResolvedValue([]);
    storeState["lastExperiment"] = evaluationOf(MEROZOITE, "exp-merozoite");
    storeState["lastExperimentSetId"] = MEROZOITE;

    renderPanels();

    await waitFor(() => {
      expect(mockListGeneSetExperiments).toHaveBeenCalledWith(GAMETOCYTE);
    });
    expect(sweepHeader().disabled).toBe(true);
    expect(enrichmentHeader().disabled).toBe(true);
    expect(screen.getAllByText("Requires a completed evaluation first")).toHaveLength(
      2,
    );
  });

  it("swaps which set is unlocked when the active set changes", async () => {
    mockListGeneSetExperiments.mockImplementation(async (geneSetId: string) =>
      geneSetId === GAMETOCYTE ? [evaluationOf(GAMETOCYTE, "exp-gametocyte")] : [],
    );

    const { rerender } = renderPanels();

    await waitFor(() => {
      expect(sweepHeader().disabled).toBe(false);
    });

    storeState["activeSetId"] = MEROZOITE;
    rerender();

    await waitFor(() => {
      expect(sweepHeader().disabled).toBe(true);
    });
    expect(enrichmentHeader().disabled).toBe(true);
    expect(mockListGeneSetExperiments).toHaveBeenCalledWith(MEROZOITE);
  });
});
