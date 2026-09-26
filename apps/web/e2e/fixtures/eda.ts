/**
 * Recorded EDA wire payloads for the browser journeys.
 *
 * Every object matches the generated schema the app validates the response
 * against, so a route answered from here reaches the same code a live answer
 * reaches. `routeEdaReads` is a no-op in the live lane.
 */

import type { Page } from "@playwright/test";

const EDA_LIVE = process.env["PATHFINDER_EDA_LIVE"] === "1";

export const SITE_ID = "plasmodb";
export const DATASET_ID = "DS_e973eadd57";
const STUDY_ID = "STUDY_e973eadd57";
const SAMPLE_ENTITY = "ENT_8151325d";
const COUNTS_ENTITY = "ENT_fd574cd6";
const TEMPERATURE_VAR = "VAR_081ab087";
export const STUDY_TITLE = "Heat shock response in sensitive mutants (LRR5, DHC)";
const ANALYSIS_ID = "a-e2e-1";
/** The site's own page for the analysis, as `services/eda/urls.py` builds it. */
export const ANALYSIS_URL = `https://plasmodb.org/plasmo/app/workspace/analyses/${DATASET_ID}/${ANALYSIS_ID}`;

export const STUDY_ROW = {
  datasetId: DATASET_ID,
  studyId: STUDY_ID,
  displayName: STUDY_TITLE,
  shortDisplayName: "Heat shock",
  description: "Heat shock response in P. falciparum 3D7 sensitive mutants",
  sourceType: "curated",
  relevance: 1,
  canSubset: true,
  canExportRows: true,
  sites: ["plasmodb"],
  notHere: null,
};

const COUNTS_UNFILTERED = [
  {
    entityId: SAMPLE_ENTITY,
    entityDisplayName: "Sample",
    count: 12,
    unfilteredCount: 12,
  },
  {
    entityId: COUNTS_ENTITY,
    entityDisplayName: "pfal3D7 htseq counts",
    count: 68640,
    unfilteredCount: 68640,
  },
];

const COUNTS_FEBRILE = [
  {
    entityId: SAMPLE_ENTITY,
    entityDisplayName: "Sample",
    count: 6,
    unfilteredCount: 12,
  },
  {
    entityId: COUNTS_ENTITY,
    entityDisplayName: "pfal3D7 htseq counts",
    count: 34320,
    unfilteredCount: 68640,
  },
];

export const FEBRILE_FILTER = {
  entityId: SAMPLE_ENTITY,
  variableId: TEMPERATURE_VAR,
  type: "stringSet",
  stringSet: ["febrile"],
};

export const FEBRILE_SUMMARY = "temperature_condition is febrile";

const FEBRILE_DISTRIBUTION = {
  variableId: TEMPERATURE_VAR,
  variableDisplayName: "temperature_condition",
  labels: ["febrile"],
  values: [6],
  subsetSize: 6,
  numVarValues: 6,
  numMissingCases: 0,
  isMultiValued: false,
};

export function analysisState(overrides: Record<string, unknown> = {}) {
  return {
    siteId: SITE_ID,
    datasetId: DATASET_ID,
    studyId: STUDY_ID,
    analysisId: ANALYSIS_ID,
    revision: 0,
    studyDisplayName: STUDY_TITLE,
    displayName: "Unsaved analysis",
    numFilters: 0,
    numComputations: 0,
    filters: [],
    filterSummaries: [],
    entityCounts: COUNTS_UNFILTERED,
    canExportRows: true,
    analysisUrl: ANALYSIS_URL,
    ...overrides,
  };
}

export const FILTERED_ANALYSIS = analysisState({
  revision: 1,
  numFilters: 1,
  filters: [FEBRILE_FILTER],
  filterSummaries: [FEBRILE_SUMMARY],
  entityCounts: COUNTS_FEBRILE,
});

/** The comparison the agent's compute records, named as the study names it. */
const COMPUTE = {
  method: "DESeq",
  identifierVariable: "Gene",
  valueVariable: "Sense Count",
  comparatorVariable: "temperature_condition",
  groupA: ["normal"],
  groupB: ["febrile"],
};

export const COMPARISON_SENTENCE =
  "DESeq compares normal (group A) with febrile (group B) on temperature_condition, reading Sense Count per Gene.";

/** The filtered analysis after the agent ran its comparison. */
export const COMPARED_ANALYSIS = analysisState({
  revision: 2,
  numFilters: 1,
  numComputations: 1,
  filters: [FEBRILE_FILTER],
  filterSummaries: [FEBRILE_SUMMARY],
  entityCounts: COUNTS_FEBRILE,
  compute: COMPUTE,
});

/** One point per gene, including the live row that carries no p-value. At the
 * default thresholds (effect 1, significance 0.05, both directions) exactly one
 * gene is selected and one point is dropped. */
export const VOLCANO_VIZ = {
  datasetId: DATASET_ID,
  analysisId: ANALYSIS_ID,
  chart: "volcano",
  effectSizeLabel: "log2(Fold Change)",
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  effectDirection: "upAndDown",
  totalPoints: 3,
  retainedPoints: 1,
  retainedPointIds: ["PF3D7_0100200"],
  points: [
    {
      pointId: "PF3D7_0100100",
      effectSize: -0.218035922112735,
      pValue: 0.350285751849808,
      adjustedPValue: 0.46960449943855,
      retained: false,
    },
    {
      pointId: "PF3D7_0100200",
      effectSize: 3.94437533216012,
      pValue: 1.95781599815607e-5,
      adjustedPValue: 0.000137772236907279,
      retained: true,
    },
    {
      pointId: "PF3D7_MIT04200",
      effectSize: -1.49447459261845,
      pValue: null,
      adjustedPValue: null,
      retained: false,
    },
  ],
};

/** The volcano route's own answer: the part without its dataset and analysis ids. */
export const VOLCANO_RESPONSE = {
  chart: VOLCANO_VIZ.chart,
  effectSizeLabel: VOLCANO_VIZ.effectSizeLabel,
  effectSizeThreshold: VOLCANO_VIZ.effectSizeThreshold,
  significanceThreshold: VOLCANO_VIZ.significanceThreshold,
  effectDirection: VOLCANO_VIZ.effectDirection,
  totalPoints: VOLCANO_VIZ.totalPoints,
  retainedPoints: VOLCANO_VIZ.retainedPoints,
  retainedPointIds: VOLCANO_VIZ.retainedPointIds,
  points: VOLCANO_VIZ.points,
  comparison: { groupA: COMPUTE.groupA, groupB: COMPUTE.groupB },
};

export const SUBSET_PREVIEW = {
  datasetId: DATASET_ID,
  analysisId: ANALYSIS_ID,
  entityCounts: COUNTS_FEBRILE,
  distribution: FEBRILE_DISTRIBUTION,
  distributionNote: null,
};

export const EXPORTED_STEP = {
  id: "step_eda_1",
  searchName: "GenesByEdaVizWithCompute",
  displayName: "Genes that differ between normal and febrile",
  estimatedSize: 1543,
};

export function exportedStrategy(conversationId: string) {
  return {
    id: conversationId,
    name: "Heat shock volcano",
    siteId: SITE_ID,
    recordType: "transcript",
    rootStepId: EXPORTED_STEP.id,
    isSaved: false,
    steps: [EXPORTED_STEP],
    createdAt: "2026-08-28T00:00:00Z",
    updatedAt: "2026-08-28T00:00:00Z",
  };
}

export function edaJson(body: unknown) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

/**
 * Answer the tab's study search and figure reads from the recorded payloads.
 *
 * Playwright tries routes in reverse registration order, and `?` is a literal
 * in a URL glob, so each pattern names the query string it expects.
 */
export async function routeEdaReads(page: Page): Promise<void> {
  if (EDA_LIVE) return;
  await page.route("**/api/v1/eda/studies?*", (route) =>
    route.fulfill(edaJson({ studies: [STUDY_ROW] })),
  );
  await page.route("**/api/v1/eda/viz?*", (route) =>
    route.fulfill(edaJson(VOLCANO_RESPONSE)),
  );
}
