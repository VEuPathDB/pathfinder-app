import type { ControlSet, Experiment, GeneSet, ParamSpec } from "@pathfinder/shared";

export const SITE_ORGANISMS = [
  "Plasmodium berghei ANKA",
  "Plasmodium falciparum 3D7",
  "Plasmodium vivax P01",
];

export const ORGANISM_SPECS: ParamSpec[] = [
  { name: "min_fold_change", type: "number" },
  {
    name: "organism",
    type: "enum",
    displayType: "treeBox",
    vocabulary: {
      data: { term: "@@fake@@", display: "All" },
      children: SITE_ORGANISMS.map((organism) => ({
        data: { term: organism, display: organism },
      })),
    },
  },
];

export const NO_ORGANISM_SPECS: ParamSpec[] = [
  { name: "min_fold_change", type: "number" },
  {
    name: "sequence_type",
    type: "enum",
    vocabulary: [
      ["genomic", "Genomic", null],
      ["protein", "Protein", null],
    ],
  },
];

function controlSet(overrides: Partial<ControlSet>): ControlSet {
  return {
    id: "cs-1",
    name: "gametocyte surface",
    siteId: "plasmodb",
    recordType: "transcript",
    positiveIds: ["PF3D7_0304600"],
    negativeIds: ["PF3D7_0930300"],
    source: "curation",
    tags: [],
    provenanceNotes: "",
    version: 1,
    isPublic: false,
    userId: null,
    createdAt: "2026-09-15T00:00:00Z",
    ...overrides,
  };
}

export const CONTROL_SETS: ControlSet[] = [
  controlSet({ id: "cs-gam", name: "gametocyte surface" }),
  controlSet({
    id: "cs-mero",
    name: "merozoite invasion",
    positiveIds: ["PF3D7_1133400"],
    negativeIds: ["PF3D7_0304600"],
  }),
];

export const SEARCH_BACKED_SET: GeneSet = {
  id: "set-1",
  name: "gametocyte secreted",
  siteId: "plasmodb",
  recordType: "transcript",
  searchName: "GenesByRNASeq",
  parameters: {
    organism: { type: "single-pick-vocabulary", value: "Plasmodium falciparum 3D7" },
  },
  geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
  geneCount: 2,
  membershipDigest: "000000000000000d",
  source: "strategy",
  createdAt: "2026-09-15T00:00:00Z",
};

/** What the workbench stores for a single-step strategy: a name, no parameters. */
export const SEARCH_WITHOUT_PARAMETERS_SET: GeneSet = {
  id: "set-1",
  name: "signal peptide candidates",
  siteId: "plasmodb",
  recordType: "transcript",
  searchName: "GenesWithSignalPeptide",
  parameters: null,
  geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
  geneCount: 2,
  membershipDigest: "000000000000000c",
  source: "strategy",
  createdAt: "2026-09-15T00:00:00Z",
};

export const GENE_LIST_SET: GeneSet = {
  id: "set-1",
  name: "gametocyte secreted",
  siteId: "plasmodb",
  recordType: "transcript",
  wdkStepId: 227292990,
  geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
  geneCount: 2,
  membershipDigest: "000000000000000b",
  source: "strategy",
  createdAt: "2026-09-15T00:00:00Z",
};

interface FailedRun {
  id: string;
  name: string;
  organism?: string;
  controlSetLabel?: string;
  error: string;
}

/** A run that raised: the API reports it beside the ones that finished. */
export function failedExperiment(run: FailedRun): Experiment {
  return {
    id: run.id,
    config: {
      siteId: "plasmodb",
      recordType: "transcript",
      searchName: "GenesByRNASeq",
      parameters:
        run.organism != null
          ? { organism: { type: "single-pick-vocabulary", value: run.organism } }
          : {},
      positiveControls: ["PF3D7_0304600"],
      negativeControls: ["PF3D7_0930300"],
      controlsSearchName: "GeneByLocusTag",
      controlsParamName: "ds_gene_ids",
      name: run.name,
    },
    status: "error",
    error: run.error,
    ...(run.controlSetLabel != null ? { controlSetLabel: run.controlSetLabel } : {}),
  };
}

interface RunOutcome {
  id: string;
  name: string;
  organism?: string;
  controlSetLabel?: string;
  precision: number;
  sensitivity: number;
  f1Score: number;
  mcc: number;
  totalResults: number;
}

/** A completed experiment carrying the metrics a comparison row prints. */
export function finishedExperiment(outcome: RunOutcome): Experiment {
  return {
    id: outcome.id,
    config: {
      siteId: "plasmodb",
      recordType: "transcript",
      searchName: "GenesByRNASeq",
      parameters:
        outcome.organism != null
          ? {
              organism: {
                type: "single-pick-vocabulary",
                value: outcome.organism,
              },
            }
          : {},
      positiveControls: ["PF3D7_0304600"],
      negativeControls: ["PF3D7_0930300"],
      controlsSearchName: "GeneByLocusTag",
      controlsParamName: "ds_gene_ids",
      name: outcome.name,
    },
    status: "completed",
    metrics: {
      confusionMatrix: {
        truePositives: 8,
        falsePositives: 2,
        trueNegatives: 8,
        falseNegatives: 2,
      },
      sensitivity: outcome.sensitivity,
      specificity: 0.8,
      precision: outcome.precision,
      f1Score: outcome.f1Score,
      mcc: outcome.mcc,
      balancedAccuracy: 0.8,
      totalResults: outcome.totalResults,
    },
    ...(outcome.controlSetLabel != null
      ? { controlSetLabel: outcome.controlSetLabel }
      : {}),
  };
}
