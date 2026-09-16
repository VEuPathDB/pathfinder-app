// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { Experiment, GeneSet } from "@pathfinder/shared";
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

vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ selectedSite: "plasmodb" }),
}));

const geneSets = vi.hoisted(() => ({ current: [] as GeneSet[] }));

vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({ data: geneSets.current }),
}));

import { CustomEnrichmentPanel } from "./CustomEnrichmentPanel";
import { SweepPanel } from "./SweepPanel";

const GAMETOCYTE = "gs-gametocyte";
const MEROZOITE = "gs-merozoite";
const SCORED_DIGEST = "7f1c0e2a";
const RETAKEN_DIGEST = "b40d9c11";

function geneSet(id: string, geneCount: number, membershipDigest: string): GeneSet {
  return {
    id,
    name: "gametocyte secreted",
    siteId: "plasmodb",
    source: "strategy",
    geneIds: [],
    geneCount,
    membershipDigest,
    createdAt: "2026-09-15T00:00:00Z",
  };
}

function evaluationOf(
  geneSetId: string,
  id: string,
  membership: { geneCount: number; digest: string } | null = {
    geneCount: 155,
    digest: SCORED_DIGEST,
  },
): Experiment {
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
    geneSetMembership: membership,
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
    geneSets.current = [geneSet(GAMETOCYTE, 155, SCORED_DIGEST)];
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
    geneSets.current = [geneSet(MEROZOITE, 90, "c0ffee11")];
    rerender();

    await waitFor(() => {
      expect(sweepHeader().disabled).toBe(true);
    });
    expect(enrichmentHeader().disabled).toBe(true);
    expect(mockListGeneSetExperiments).toHaveBeenCalledWith(MEROZOITE);
  });

  it("locks both once the set holds genes the evaluation never scored", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      evaluationOf(GAMETOCYTE, "exp-gametocyte"),
    ]);
    geneSets.current = [geneSet(GAMETOCYTE, 168, RETAKEN_DIGEST)];

    renderPanels();

    await waitFor(() => {
      expect(
        screen.getAllByText(
          "The evaluation scored 155 genes and this set now holds 168. " +
            "Re-evaluate to use this panel.",
        ),
      ).toHaveLength(2);
    });
    expect(sweepHeader().disabled).toBe(true);
    expect(enrichmentHeader().disabled).toBe(true);
  });

  it("locks both when the evaluation records no membership to check", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      evaluationOf(GAMETOCYTE, "exp-gametocyte", null),
    ]);

    renderPanels();

    await waitFor(() => {
      expect(
        screen.getAllByText(
          "The evaluation does not record which genes it scored. " +
            "Re-evaluate to use this panel.",
        ),
      ).toHaveLength(2);
    });
    expect(sweepHeader().disabled).toBe(true);
    expect(enrichmentHeader().disabled).toBe(true);
  });
});
