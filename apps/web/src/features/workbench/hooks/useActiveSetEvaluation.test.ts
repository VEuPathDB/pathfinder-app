// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
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

import { useActiveSetEvaluation } from "./useActiveSetEvaluation";

const GAMETOCYTE = "gs-gametocyte";
const MEROZOITE = "gs-merozoite";
const SCORED_DIGEST = "7f1c0e2a";

function geneSet(id: string, geneCount: number, membershipDigest: string): GeneSet {
  return {
    id,
    name: id,
    siteId: "plasmodb",
    source: "strategy",
    geneIds: [],
    geneCount,
    membershipDigest,
    createdAt: "2026-09-15T00:00:00Z",
  };
}

function experiment(
  id: string,
  status: NonNullable<Experiment["status"]>,
  geneCount = 155,
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
      geneSetId: GAMETOCYTE,
    },
    status,
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
    geneSetMembership: { geneCount, digest: SCORED_DIGEST },
  };
}

function render() {
  const { Wrapper } = createTestWrapper();
  return renderHook(() => useActiveSetEvaluation(), { wrapper: Wrapper });
}

describe("useActiveSetEvaluation", () => {
  beforeEach(() => {
    mockListGeneSetExperiments.mockReset();
    mockListGeneSetExperiments.mockResolvedValue([]);
    storeState["activeSetId"] = GAMETOCYTE;
    storeState["lastExperiment"] = null;
    storeState["lastExperimentSetId"] = null;
    geneSets.current = [geneSet(GAMETOCYTE, 155, SCORED_DIGEST)];
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("answers nothing when no set is active", () => {
    storeState["activeSetId"] = null;

    expect(render().result.current).toBe(null);
  });

  it("reads the stored evaluation against the set it belongs to", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      experiment("exp-gametocyte", "completed"),
    ]);

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.experiment.id).toBe("exp-gametocyte");
    });
    expect(result.current?.currency).toBe("current");
    expect(result.current?.setGeneCount).toBe(155);
  });

  it("answers with the newest evaluation the route lists first", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      experiment("exp-newer", "completed"),
      experiment("exp-older", "completed"),
    ]);

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.experiment.id).toBe("exp-newer");
    });
  });

  it("answers nothing when the set was never evaluated", async () => {
    mockListGeneSetExperiments.mockResolvedValue([]);

    const { result } = render();

    await waitFor(() => {
      expect(mockListGeneSetExperiments).toHaveBeenCalledTimes(1);
    });
    expect(result.current).toBe(null);
  });

  it("ignores a run that never completed", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      experiment("exp-running", "running"),
    ]);

    const { result } = render();

    await waitFor(() => {
      expect(mockListGeneSetExperiments).toHaveBeenCalledWith(GAMETOCYTE);
    });
    expect(result.current).toBe(null);
  });

  it("prefers the run this tab has just finished for the active set", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      experiment("exp-stored", "completed"),
    ]);
    storeState["lastExperiment"] = experiment("exp-just-run", "completed");
    storeState["lastExperimentSetId"] = GAMETOCYTE;

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.experiment.id).toBe("exp-just-run");
    });
  });

  it("ignores a just-finished run that belongs to another set", async () => {
    storeState["lastExperiment"] = experiment("exp-merozoite", "completed");
    storeState["lastExperimentSetId"] = MEROZOITE;

    const { result } = render();

    await waitFor(() => {
      expect(mockListGeneSetExperiments).toHaveBeenCalledWith(GAMETOCYTE);
    });
    expect(result.current).toBe(null);
  });

  it("reports a set whose membership has moved as superseded", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      experiment("exp-gametocyte", "completed"),
    ]);
    geneSets.current = [geneSet(GAMETOCYTE, 168, "b40d9c11")];

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.currency).toBe("superseded");
    });
    expect(result.current?.scoredGeneCount).toBe(155);
    expect(result.current?.setGeneCount).toBe(168);
  });
});
