import { describe, expect, it } from "vitest";
import type { GeneSet } from "@pathfinder/shared";
import { createExperimentRequestSchema } from "@pathfinder/shared/generated/zod/createExperimentRequestSchema";

import {
  experimentBase,
  experimentBasis,
  experimentName,
  organismBlocked,
} from "./experimentBase";

const GENE_IDS = ["PF3D7_0304600", "PF3D7_1133400", "PF3D7_0930300"];

function geneSet(overrides: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs-gametocyte-secreted",
    name: "gametocyte secreted",
    siteId: "plasmodb",
    geneIds: GENE_IDS,
    source: "strategy",
    geneCount: GENE_IDS.length,
    membershipDigest: "000000000000000e",
    recordType: "transcript",
    createdAt: "2026-09-15T00:00:00Z",
    ...overrides,
  };
}

const SEARCH_SET = geneSet({
  searchName: "GenesByRNASeq",
  parameters: {
    organism: { type: "single-pick-vocabulary", value: "Plasmodium falciparum 3D7" },
  },
});

describe("experimentBasis", () => {
  it("reads a set that records a search and its parameters as a search", () => {
    expect(experimentBasis(SEARCH_SET)).toEqual({
      kind: "search",
      searchName: "GenesByRNASeq",
      parameters: SEARCH_SET.parameters,
    });
  });

  it("reads a set that records only genes as a fixed gene list", () => {
    expect(experimentBasis(geneSet({ wdkStepId: 227292990 }))).toEqual({
      kind: "geneList",
      geneIds: GENE_IDS,
    });
  });

  it("reads a search name with no parameters as a fixed gene list", () => {
    const set = geneSet({ searchName: "GenesWithSignalPeptide", parameters: null });

    expect(experimentBasis(set).kind).toBe("geneList");
  });

  it("reads empty parameters as no recorded parameters", () => {
    const set = geneSet({ searchName: "GenesWithSignalPeptide", parameters: {} });

    expect(experimentBasis(set).kind).toBe("geneList");
  });

  it("reads a combine step as no search at all", () => {
    const set = geneSet({
      searchName: "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
      parameters: {
        bq_operator: { type: "string", value: "INTERSECT" },
      },
    });

    expect(experimentBasis(set).kind).toBe("geneList");
  });

  it("reads an empty set as nothing to run", () => {
    expect(experimentBasis(geneSet({ geneIds: [], geneCount: 0 })).kind).toBe("none");
  });
});

describe("organismBlocked", () => {
  it("allows a base that records a search", () => {
    expect(organismBlocked(SEARCH_SET)).toBe(null);
  });

  it("does not claim a set records no search when it records one", () => {
    const set = geneSet({ searchName: "GenesWithSignalPeptide", parameters: null });

    expect(organismBlocked(set)).toBe(
      "This set records the search GenesWithSignalPeptide but not the parameters " +
        "it ran with, so there is nothing for an organism to vary.",
    );
  });

  it("names the reason a fixed gene list cannot vary by organism", () => {
    expect(organismBlocked(geneSet())).toBe(
      "This set holds a fixed gene list and records no search, so an organism " +
        "changes nothing. Evaluate or Benchmark it instead.",
    );
  });

  it("names a combine step for what it is", () => {
    const set = geneSet({
      searchName: "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
    });

    expect(organismBlocked(set)).toBe(
      "This set was saved from a step that combines two others, which runs no " +
        "search of its own, so an organism changes nothing.",
    );
  });

  it("names the reason an empty set cannot run at all", () => {
    expect(organismBlocked(geneSet({ geneIds: [], geneCount: 0 }))).toBe(
      "This set holds no genes and records no search, so there is nothing to run.",
    );
  });
});

describe("experimentName", () => {
  it("names the run after the set", () => {
    expect(experimentName("gametocyte secreted", "batch")).toBe(
      "gametocyte secreted (batch)",
    );
  });

  it("keeps a long set name inside the 200 characters the API accepts", () => {
    const long = "P".repeat(250);

    const named = experimentName(long, "evaluation");

    expect(named).toHaveLength(200);
    expect(named.endsWith("... (evaluation)")).toBe(true);
  });

  it("leaves a name that just fits untouched", () => {
    const exact = "P".repeat(192);

    expect(experimentName(exact, "batch")).toBe(`${exact} (batch)`);
  });
});

describe("experimentBase", () => {
  it("builds a request the API accepts from a search-backed set", () => {
    const base = experimentBase({
      geneSet: SEARCH_SET,
      positiveControls: ["PF3D7_0304600"],
      negativeControls: ["PF3D7_0930300"],
      run: "batch",
    });

    expect(createExperimentRequestSchema.safeParse(base).success).toBe(true);
    expect(base.controlsSearchName).toBe("GeneByLocusTag");
    expect(base.controlsParamName).toBe("ds_gene_ids");
    expect(base.recordType).toBe("transcript");
    expect(base.searchName).toBe("GenesByRNASeq");
    expect(base.targetGeneIds).toBe(null);
    expect(base.geneSetId).toBe("gs-gametocyte-secreted");
    expect(base.name).toBe("gametocyte secreted (batch)");
  });

  it("evaluates a gene-list set against its own genes", () => {
    const base = experimentBase({
      geneSet: geneSet({ wdkStepId: 227292990 }),
      positiveControls: ["PF3D7_0304600"],
      negativeControls: [],
      run: "benchmark",
    });

    expect(createExperimentRequestSchema.safeParse(base).success).toBe(true);
    expect(base.targetGeneIds).toEqual(GENE_IDS);
    expect(base.searchName).toBe("");
  });

  it("sends a name the API accepts for a set named up to its own limit", () => {
    const base = experimentBase({
      geneSet: geneSet({ name: "P".repeat(200) }),
      positiveControls: ["PF3D7_0304600"],
      negativeControls: [],
      run: "evaluation",
    });

    expect(createExperimentRequestSchema.safeParse(base).success).toBe(true);
    expect(base.name).toHaveLength(200);
  });

  it("falls back to the gene record type when the set records none", () => {
    const base = experimentBase({
      geneSet: geneSet({ recordType: null }),
      positiveControls: ["PF3D7_0304600"],
      negativeControls: [],
      run: "evaluation",
    });

    expect(base.recordType).toBe("gene");
  });
});
