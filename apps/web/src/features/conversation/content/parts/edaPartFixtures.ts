import type { EdaAnalysisState, EdaSubsetPreview, EdaViz } from "@pathfinder/shared";

export const EDA_ANALYSIS_STATE_FIXTURE: EdaAnalysisState = {
  siteId: "plasmodb",
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  analysisId: "a-1",
  revision: 3,
  studyDisplayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
  displayName: "Febrile samples",
  numFilters: 2,
  numComputations: 1,
  filters: [
    {
      entityId: "ENT_8151325d",
      variableId: "VAR_081ab087",
      type: "stringSet",
      stringSet: ["febrile"],
    },
    {
      entityId: "ENT_8151325d",
      variableId: "VAR_7033e90f",
      type: "numberRange",
      min: 37,
      max: 42,
    },
  ],
  filterSummaries: ["temperature_condition is febrile", "Temperature is 37 to 42"],
  entityCounts: [
    {
      entityId: "ENT_8151325d",
      entityDisplayName: "Sample",
      count: 6,
      unfilteredCount: 12,
    },
    {
      entityId: "ENT_fd574cd6",
      entityDisplayName: "pfal3D7 htseq counts",
      count: 34320,
      unfilteredCount: 68640,
    },
  ],
  canExportRows: true,
};

export const EDA_SUBSET_PREVIEW_FIXTURE: EdaSubsetPreview = {
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  entityCounts: [
    {
      entityId: "ENT_8151325d",
      entityDisplayName: "Sample",
      count: 6,
      unfilteredCount: 12,
    },
  ],
  distribution: {
    variableId: "VAR_7033e90f",
    variableDisplayName: "Temperature",
    labels: ["[37, 38)", "[41, 42]"],
    values: [6, 6],
    subsetSize: 6,
    numVarValues: 6,
    numMissingCases: 0,
    isMultiValued: false,
  },
  distributionNote: null,
};

export const EDA_VOLCANO_VIZ_FIXTURE: EdaViz = {
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
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

export const EDA_SCATTER_VIZ_FIXTURE: EdaViz = {
  ...EDA_VOLCANO_VIZ_FIXTURE,
  chart: "scatter",
};
