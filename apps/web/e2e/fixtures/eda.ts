/**
 * Recorded EDA wire payloads for the three browser journeys.
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
export const SAMPLE_ENTITY = "ENT_8151325d";
const COUNTS_ENTITY = "ENT_fd574cd6";
export const TEMPERATURE_VAR = "VAR_081ab087";
export const STUDY_TITLE = "Heat shock response in sensitive mutants (LRR5, DHC)";

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
};

/** The flat detail the tab reads: an entity names its parent, a variable names
 * its entity, and the server has already derived every filter type. */
export const STUDY_DETAIL = {
  datasetId: DATASET_ID,
  studyId: STUDY_ID,
  displayName: STUDY_TITLE,
  entities: [
    {
      entityId: SAMPLE_ENTITY,
      displayName: "Sample",
      displayNamePlural: "Samples",
      parentEntityId: null,
      variableCount: 1,
      hasGeneId: false,
    },
    {
      entityId: COUNTS_ENTITY,
      displayName: "pfal3D7 htseq counts",
      displayNamePlural: "pfal3D7 htseq counts",
      parentEntityId: SAMPLE_ENTITY,
      variableCount: 2,
      hasGeneId: true,
    },
  ],
  variables: [
    {
      entityId: SAMPLE_ENTITY,
      variableId: TEMPERATURE_VAR,
      displayName: "temperature_condition",
      variableType: "string",
      filterType: "stringSet",
      dataShape: "categorical",
      isMultiValued: false,
      vocabulary: ["febrile", "normal"],
      vocabularyTotal: 2,
      vocabularyNote: null,
      rangeMin: null,
      rangeMax: null,
      dateMin: null,
      dateMax: null,
      subFilterVariableIds: [],
      hideFrom: [],
    },
    {
      entityId: COUNTS_ENTITY,
      variableId: "VEUPATHDB_GENE_ID",
      displayName: "Gene ID",
      variableType: "string",
      filterType: "stringSet",
      dataShape: "categorical",
      isMultiValued: false,
      vocabulary: [],
      vocabularyTotal: 5720,
      vocabularyNote: "5720 values; the first 0 are listed",
      rangeMin: null,
      rangeMax: null,
      dateMin: null,
      dateMax: null,
      subFilterVariableIds: [],
      hideFrom: [],
    },
    {
      entityId: COUNTS_ENTITY,
      variableId: "SEQUENCE_READ_COUNT_SENSE",
      displayName: "Read count, sense",
      variableType: "integer",
      filterType: "numberRange",
      dataShape: "continuous",
      isMultiValued: false,
      vocabulary: [],
      vocabularyTotal: 0,
      vocabularyNote: null,
      rangeMin: 0,
      rangeMax: 68640,
      dateMin: null,
      dateMax: null,
      subFilterVariableIds: [],
      hideFrom: [],
    },
  ],
  geneEntityId: COUNTS_ENTITY,
  geneEntityProblem: null,
  canSubset: true,
  canExportRows: true,
};

export const COUNTS_UNFILTERED = [
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

export const COUNTS_FEBRILE = [
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

export const FEBRILE_DISTRIBUTION = {
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
    analysisId: "a-e2e-1",
    revision: 0,
    studyDisplayName: STUDY_TITLE,
    displayName: "Unsaved analysis",
    numFilters: 0,
    numComputations: 0,
    filters: [],
    filterSummaries: [],
    entityCounts: COUNTS_UNFILTERED,
    canExportRows: true,
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

/** One point per gene, including the live row that carries no p-value. At the
 * default thresholds (effect 1, significance 0.05, both directions) exactly one
 * gene is selected and one point is dropped. */
export const VOLCANO_VIZ = {
  datasetId: DATASET_ID,
  analysisId: "a-e2e-1",
  chart: "volcano",
  effectSizeLabel: "log2(Fold Change)",
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  effectDirection: "upAndDown",
  totalPoints: 3,
  retainedPoints: 1,
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

export const SUBSET_PREVIEW = {
  datasetId: DATASET_ID,
  analysisId: "a-e2e-1",
  entityCounts: COUNTS_FEBRILE,
  distribution: FEBRILE_DISTRIBUTION,
  distributionNote: null,
};

export const COMPUTE_JOB = {
  jobId: "db04204e5386396e1ca2cb78469ab6fb",
  taskId: null,
  appName: "differentialexpression",
  status: "complete",
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
 * Answer the tab's study and subset reads from the recorded payloads.
 *
 * A count request names one entity, so the answer is that entity's row, taken
 * from the filtered table when the request carries a filter. The detail pattern
 * registers last so it wins over the search pattern: Playwright tries routes in
 * reverse registration order, and `?` is a literal in a URL glob, so
 * `studies?*` never matches `studies/DS_...`.
 */
export async function routeEdaReads(page: Page): Promise<void> {
  if (EDA_LIVE) return;
  await page.route("**/api/v1/eda/count?*", (route) => {
    const body = route.request().postDataJSON() as {
      entityId: string;
      filters?: unknown[];
    };
    const table =
      (body.filters ?? []).length === 0 ? COUNTS_UNFILTERED : COUNTS_FEBRILE;
    const row = table.find((entry) => entry.entityId === body.entityId);
    if (row === undefined) throw new Error(`no count fixture for ${body.entityId}`);
    return route.fulfill(
      edaJson({
        entityId: row.entityId,
        count: row.count,
        unfilteredCount: row.unfilteredCount,
      }),
    );
  });
  await page.route("**/api/v1/eda/distribution?*", (route) =>
    route.fulfill(edaJson(FEBRILE_DISTRIBUTION)),
  );
  await page.route("**/api/v1/eda/studies?*", (route) =>
    route.fulfill(edaJson({ studies: [STUDY_ROW] })),
  );
  await page.route(`**/api/v1/eda/studies/${DATASET_ID}*`, (route) =>
    route.fulfill(edaJson(STUDY_DETAIL)),
  );
}
