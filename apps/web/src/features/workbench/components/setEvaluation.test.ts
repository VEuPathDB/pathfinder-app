import { describe, expect, it } from "vitest";
import type { Experiment, GeneSet } from "@pathfinder/shared";

import { evaluatedLabel, evaluationBlock, setEvaluation } from "./setEvaluation";

const SCORED_DIGEST = "a1b2c3d4e5f6";
const OTHER_DIGEST = "ffffffffffff";

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
    geneSetMembership: { geneCount: 155, digest: SCORED_DIGEST },
    ...overrides,
  };
}

function geneSet(geneCount: number, membershipDigest: string): GeneSet {
  return {
    id: "gs-gametocyte",
    name: "gametocyte secreted",
    siteId: "plasmodb",
    source: "strategy",
    geneIds: [],
    geneCount,
    membershipDigest,
    createdAt: "2026-09-15T00:00:00Z",
  };
}

describe("setEvaluation", () => {
  it("is current when the evaluation scored the membership the set holds", () => {
    const evaluation = setEvaluation(experiment({}), geneSet(155, SCORED_DIGEST));

    expect(evaluation?.currency).toBe("current");
    expect(evaluation?.scoredGeneCount).toBe(155);
    expect(evaluation?.setGeneCount).toBe(155);
  });

  it("is superseded when the set holds a different membership now", () => {
    const evaluation = setEvaluation(experiment({}), geneSet(168, OTHER_DIGEST));

    expect(evaluation?.currency).toBe("superseded");
    expect(evaluation?.scoredGeneCount).toBe(155);
    expect(evaluation?.setGeneCount).toBe(168);
  });

  it("is superseded when a set of the same size holds different genes", () => {
    const evaluation = setEvaluation(experiment({}), geneSet(155, OTHER_DIGEST));

    expect(evaluation?.currency).toBe("superseded");
  });

  it("is unrecorded when the evaluation names no membership", () => {
    const evaluation = setEvaluation(
      experiment({ geneSetMembership: null }),
      geneSet(155, SCORED_DIGEST),
    );

    expect(evaluation?.currency).toBe("unrecorded");
    expect(evaluation?.scoredGeneCount).toBe(null);
  });

  it("is nothing for a set that was never evaluated", () => {
    expect(setEvaluation(null, geneSet(155, SCORED_DIGEST))).toBe(null);
  });

  it("is nothing while the set it belongs to is still loading", () => {
    expect(setEvaluation(experiment({}), undefined)).toBe(null);
  });
});

describe("evaluatedLabel", () => {
  it("names the day a current evaluation finished", () => {
    expect(
      evaluatedLabel(setEvaluation(experiment({}), geneSet(155, SCORED_DIGEST))),
    ).toBe("Evaluated Sep 15, 2026");
  });

  it("falls back to the day the run started when it recorded no finish", () => {
    const evaluation = setEvaluation(
      experiment({ completedAt: null }),
      geneSet(155, SCORED_DIGEST),
    );

    expect(evaluatedLabel(evaluation)).toBe("Evaluated Sep 14, 2026");
  });

  it("says only that an evaluation exists when it carries no readable time", () => {
    const evaluation = setEvaluation(
      experiment({ completedAt: null, createdAt: "" }),
      geneSet(155, SCORED_DIGEST),
    );

    expect(evaluatedLabel(evaluation)).toBe("Evaluated");
  });

  it("says a superseded evaluation is out of date and how many it scored", () => {
    const evaluation = setEvaluation(experiment({}), geneSet(168, OTHER_DIGEST));

    expect(evaluatedLabel(evaluation)).toBe(
      "Evaluated Sep 15, 2026 (scored 155 genes, out of date)",
    );
  });

  it("says an unrecorded evaluation does not name its genes", () => {
    const evaluation = setEvaluation(
      experiment({ geneSetMembership: null }),
      geneSet(155, SCORED_DIGEST),
    );

    expect(evaluatedLabel(evaluation)).toBe(
      "Evaluated Sep 15, 2026 (genes not recorded)",
    );
  });

  it("says nothing for a set with no evaluation", () => {
    expect(evaluatedLabel(null)).toBe(null);
  });
});

describe("evaluationBlock", () => {
  it("lets a panel open on a current evaluation", () => {
    expect(
      evaluationBlock(setEvaluation(experiment({}), geneSet(155, SCORED_DIGEST))),
    ).toBe(null);
  });

  it("asks for an evaluation when the set has none", () => {
    expect(evaluationBlock(null)).toBe("Requires a completed evaluation first");
  });

  it("names both counts when the set has moved since it was evaluated", () => {
    expect(
      evaluationBlock(setEvaluation(experiment({}), geneSet(168, OTHER_DIGEST))),
    ).toBe(
      "The evaluation scored 155 genes and this set now holds 168. " +
        "Re-evaluate to use this panel.",
    );
  });

  it("says an unrecorded evaluation cannot be checked against the set", () => {
    const evaluation = setEvaluation(
      experiment({ geneSetMembership: null }),
      geneSet(155, SCORED_DIGEST),
    );

    expect(evaluationBlock(evaluation)).toBe(
      "The evaluation does not record which genes it scored. " +
        "Re-evaluate to use this panel.",
    );
  });
});
