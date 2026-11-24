import type { SharedContext } from "@strategist/shared/generated/types/SharedContext";

import { EDA_ANALYSIS_STATE_FIXTURE } from "../content/parts/edaPartFixtures";

export const SHARED_CONTEXT: SharedContext = {
  strategy: {
    id: "0b5a2f8e-4c1d-5e2f-9a3b-6c7d8e9f0a1b",
    name: "kinases",
    siteId: "plasmodb",
    recordType: "transcript",
    rootStepId: "s-both",
    isSaved: false,
    wdkUrl: null,
    wdkStrategyId: null,
    createdAt: "2026-11-23T00:00:00Z",
    updatedAt: "2026-11-23T00:00:00Z",
    steps: [
      {
        id: "s-list",
        kind: "search",
        displayName: "Gene set: 3D7 strain gaps",
        searchName: "GeneByLocusTag",
        recordType: "transcript",
        parameters: {},
        isFiltered: false,
        estimatedSize: 41,
        wdkStepId: null,
      },
      {
        id: "s-text",
        kind: "search",
        displayName: "Genes by text",
        searchName: "GenesByText",
        recordType: "transcript",
        parameters: { text_expression: { type: "string", value: "kinase" } },
        isFiltered: false,
        estimatedSize: 1204,
        wdkStepId: null,
      },
      {
        id: "s-both",
        kind: "combine",
        displayName: "Both",
        operator: "INTERSECT",
        recordType: "transcript",
        primaryInputStepId: "s-list",
        secondaryInputStepId: "s-text",
        isFiltered: false,
        estimatedSize: 12,
        wdkStepId: null,
      },
    ],
  },
  study: { ...EDA_ANALYSIS_STATE_FIXTURE, analysisUrl: null, canExportRows: false },
  privateInputs: { "s-list": ["ds_gene_ids"] },
};
