/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { createTestWrapper } from "@/lib/query/testing";
import type { Experiment } from "@pathfinder/shared";

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
  activeSetId: null as string | null,
  lastExperiment: null as Experiment | null,
  lastExperimentSetId: null as string | null,
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(storeState),
}));

import { useActiveSetExperiment } from "./useActiveSetExperiment";

function makeExperiment(overrides: Partial<Experiment> & { id: string }): Experiment {
  return {
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
      geneSetId: "gs-gametocyte",
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
    ...overrides,
  };
}

function render() {
  const { Wrapper } = createTestWrapper();
  return renderHook(() => useActiveSetExperiment(), { wrapper: Wrapper });
}

describe("useActiveSetExperiment", () => {
  beforeEach(() => {
    mockListGeneSetExperiments.mockReset();
    storeState["activeSetId"] = "gs-gametocyte";
    storeState["lastExperiment"] = null;
    storeState["lastExperimentSetId"] = null;
  });

  it("answers with the stored evaluation of the active set", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      makeExperiment({ id: "exp-stored" }),
    ]);

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.id).toBe("exp-stored");
    });
    expect(mockListGeneSetExperiments).toHaveBeenCalledWith("gs-gametocyte");
  });

  it("answers with the newest completed evaluation the route lists first", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      makeExperiment({ id: "exp-newer", createdAt: "2026-09-15T10:00:00Z" }),
      makeExperiment({ id: "exp-older", createdAt: "2026-09-14T10:00:00Z" }),
    ]);

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.id).toBe("exp-newer");
    });
  });

  it("skips an evaluation that did not complete", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      makeExperiment({ id: "exp-failed", status: "error", error: "WDK timed out" }),
      makeExperiment({ id: "exp-done" }),
    ]);

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.id).toBe("exp-done");
    });
  });

  it("answers with nothing when the set was never evaluated", async () => {
    mockListGeneSetExperiments.mockResolvedValue([]);

    const { result } = render();

    await waitFor(() => {
      expect(mockListGeneSetExperiments).toHaveBeenCalledTimes(1);
    });
    expect(result.current).toBeNull();
  });

  it("answers with nothing and asks nothing when no set is active", () => {
    storeState["activeSetId"] = null;

    const { result } = render();

    expect(result.current).toBeNull();
    expect(mockListGeneSetExperiments).not.toHaveBeenCalled();
  });

  it("prefers the run this tab just finished over the stored one", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      makeExperiment({ id: "exp-stored" }),
    ]);
    storeState["lastExperiment"] = makeExperiment({ id: "exp-just-run" });
    storeState["lastExperimentSetId"] = "gs-gametocyte";

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.id).toBe("exp-just-run");
    });
  });

  it("ignores a run this tab finished for a different set", async () => {
    mockListGeneSetExperiments.mockResolvedValue([
      makeExperiment({ id: "exp-stored" }),
    ]);
    storeState["lastExperiment"] = makeExperiment({ id: "exp-other-set" });
    storeState["lastExperimentSetId"] = "gs-merozoite";

    const { result } = render();

    await waitFor(() => {
      expect(result.current?.id).toBe("exp-stored");
    });
  });
});
