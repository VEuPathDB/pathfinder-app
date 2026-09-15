import { describe, expect, it } from "vitest";
import type { Experiment } from "@pathfinder/shared";

import { evaluatedLabel } from "./evaluatedLabel";

function experiment(overrides: Partial<Experiment>): Experiment {
  return {
    id: "exp-1",
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
    createdAt: "2026-09-14T12:00:00Z",
    completedAt: "2026-09-15T12:00:00Z",
    wdkStrategyId: null,
    wdkStepId: null,
    robustness: null,
    ...overrides,
  };
}

describe("evaluatedLabel", () => {
  it("names the day the evaluation finished", () => {
    expect(evaluatedLabel(experiment({}))).toBe("Evaluated Sep 15, 2026");
  });

  it("falls back to the day the run started when it recorded no finish", () => {
    expect(evaluatedLabel(experiment({ completedAt: null }))).toBe(
      "Evaluated Sep 14, 2026",
    );
  });

  it("says only that an evaluation exists when it carries no readable time", () => {
    expect(evaluatedLabel(experiment({ completedAt: null, createdAt: "" }))).toBe(
      "Evaluated",
    );
  });

  it("says nothing for a set with no evaluation", () => {
    expect(evaluatedLabel(null)).toBe(null);
  });
});
