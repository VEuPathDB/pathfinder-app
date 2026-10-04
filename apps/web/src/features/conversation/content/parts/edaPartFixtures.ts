import type {
  EdaAnalysisState,
  EdaPcaPart,
  EdaStatisticsPart,
  EdaSubsetPreview,
  EdaViz,
} from "@pathfinder/shared";

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

export const EDA_PCA_FIXTURE: EdaPcaPart = {
  statisticId: "stat_f8ca8214",
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  axes: [
    { variableId: "PC1", displayName: "PC 1 (54.35% variance)" },
    { variableId: "PC2", displayName: "PC 2 (12.79% variance)" },
  ],
  series: [
    {
      label: "delta-DHC mutant",
      x: [-32.8759958003351, -45.3261209288939, 37.2967855338906, 17.5188028100268],
      y: [-18.1168003956837, -13.2272286120369, -23.0828400229326, -23.4888748407649],
      sampleIds: ["PB4_37C_Rep1", "PB4_37C_Rep2", "PB4_41C_Rep1", "PB4_41C_Rep2"],
    },
    {
      label: "delta-LRR5 mutant",
      x: [-61.4351512946123, -50.227058404734, 0.443609763729234, 45.4558380786033],
      y: [43.0792816268799, 10.9447707441747, 5.12424133133646, 1.92767239157473],
      sampleIds: ["PB31_37C_Rep1", "PB31_37C_Rep2", "PB31_41C_Rep1", "PB31_41C_Rep2"],
    },
    {
      label: "wildtype",
      x: [-7.2548330125957, -26.8849459871985, 59.7446980845019, 63.5443711576177],
      y: [-19.2972293300329, -9.22066006555882, 22.7506369532308, 22.6070302198135],
      sampleIds: ["WT_37C_Rep1", "WT_37C_Rep2", "WT_41C_Rep1", "WT_41C_Rep2"],
    },
  ],
  caption: "The samples separate by temperature along the first component",
  sampleCount: 12,
  groupCount: 3,
};

export const EDA_CONTINGENCY_FIXTURE: EdaStatisticsPart = {
  statisticId: "stat_e5acf8e3",
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  kind: "contingency",
  title: "Contingency table of genotype by temperature_condition",
  rows: [
    { name: "chi-squared", value: "0", pValue: "1", confidenceInterval: null },
    { name: "degrees of freedom", value: "2", pValue: null, confidenceInterval: null },
  ],
  table: {
    xLabels: ["delta-DHC mutant", "delta-LRR5 mutant", "wildtype"],
    yLabels: ["febrile", "normal"],
    matrix: [
      [2, 2],
      [2, 2],
      [2, 2],
    ],
  },
  boxes: [],
  trend: null,
  caption: "Each genotype was sampled in both conditions",
};

export const EDA_TWO_BY_TWO_FIXTURE: EdaStatisticsPart = {
  statisticId: "stat_f36409b6",
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  kind: "two_by_two",
  title: "Two-by-two table of temperature_condition by genotype",
  rows: [
    { name: "chi-squared", value: "0.5", pValue: "0.4795", confidenceInterval: "NA" },
    {
      name: "Fisher's exact",
      value: "9",
      pValue: "0.4857",
      confidenceInterval: "0.3 - 271.9",
    },
    {
      name: "odds ratio",
      value: "9",
      pValue: "0.4857",
      confidenceInterval: "0.3 - 271.9",
    },
    {
      name: "relative risk",
      value: "3",
      pValue: "0.4857",
      confidenceInterval: "0.5 - 18.1",
    },
  ],
  table: {
    xLabels: ["febrile", "normal"],
    yLabels: ["wildtype", "delta-DHC mutant"],
    matrix: [
      [3, 1],
      [1, 3],
    ],
  },
  boxes: [],
  trend: null,
  caption: "",
};

export const EDA_BOXPLOT_FIXTURE: EdaStatisticsPart = {
  statisticId: "stat_83e25cb8",
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  kind: "boxplot",
  title: "Box plot of Sense Count by genotype",
  rows: [],
  table: null,
  boxes: [
    {
      label: "delta-DHC mutant",
      lowerFence: 0,
      q1: 0,
      median: 1,
      q3: 4.5,
      upperFence: 6,
      mean: 61.1667,
      outlierCount: 4,
    },
    {
      label: "delta-LRR5 mutant",
      lowerFence: 0,
      q1: 0,
      median: 1,
      q3: 5.25,
      upperFence: 8,
      mean: 52.4583,
      outlierCount: 4,
    },
    {
      label: "wildtype",
      lowerFence: 0,
      q1: 1,
      median: 13.5,
      q3: 45.5,
      upperFence: 49,
      mean: 76.7083,
      outlierCount: 4,
    },
  ],
  trend: null,
  caption: "",
};

export const EDA_TREND_FIXTURE: EdaStatisticsPart = {
  statisticId: "stat_dd7503b2",
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  kind: "trend",
  title: "Best-fit line of Antisense Count on Sense Count",
  rows: [
    { name: "r-squared", value: "0.106", pValue: null, confidenceInterval: null },
    { name: "points", value: "36 points", pValue: null, confidenceInterval: null },
  ],
  table: null,
  boxes: [],
  trend: {
    xLabel: "Sense Count",
    yLabel: "Antisense Count",
    x: [
      392, 8, 2, 5, 0, 1, 238, 4, 1, 6, 0, 3, 288, 6, 4, 1, 0, 0, 437, 6, 2, 2, 0, 1,
      205, 28, 15, 45, 0, 1, 328, 36, 18, 47, 0, 4,
    ],
    y: [
      9, 3, 1, 26, 2, 3, 16, 15, 0, 35, 0, 0, 9, 9, 3, 10, 1, 1, 19, 10, 0, 22, 1, 3,
      11, 2, 3, 7, 0, 1, 13, 1, 0, 11, 1, 0,
    ],
    lineX: [
      0, 1, 2, 3, 4, 5, 6, 8, 15, 18, 28, 36, 45, 47, 205, 238, 288, 328, 392, 437,
    ],
    lineY: [
      5.5487, 5.5713, 5.5939, 5.6166, 5.6392, 5.6618, 5.6844, 5.7296, 5.8878, 5.9557,
      6.1818, 6.3626, 6.5661, 6.6113, 10.1834, 10.9295, 12.0599, 12.9642, 14.4111,
      15.4285,
    ],
  },
  caption: "",
};
