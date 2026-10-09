import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import type { Page } from "@playwright/test";

export const NEEDS_QA_RECORDING =
  "needs a QA recording: re-record once QA access exists";

export const EDA_RECORDING_FILE = path.join(__dirname, "recordings", "eda.json");

interface EntityCount {
  entityId: string;
  entityDisplayName: string;
  count: number;
  unfilteredCount: number;
}

interface VolcanoPoint {
  pointId: string;
  effectSize: number;
  pValue: number | null;
  adjustedPValue: number | null;
  retained: boolean;
}

interface EdaRecording {
  siteId: string;
  datasetId: string;
  studyId: string;
  analysisId: string;
  studyTitle: string;
  analysisUrl: string;
  studyRow: Record<string, unknown>;
  countsUnfiltered: EntityCount[];
  countsFebrile: EntityCount[];
  febrileFilter: {
    entityId: string;
    variableId: string;
    type: string;
    stringSet: string[];
  };
  febrileSummary: string;
  febrileDistribution: {
    labels: string[];
    values: number[];
    subsetSize: number;
    numVarValues: number;
  } & Record<string, unknown>;
  compute: { groupA: string[]; groupB: string[] } & Record<string, unknown>;
  comparisonSentence: string;
  volcano: {
    chart: string;
    effectSizeLabel: string;
    effectSizeThreshold: number;
    significanceThreshold: number;
    effectDirection: string;
    totalPoints: number;
    retainedPoints: number;
    retainedPointIds: string[];
    points: VolcanoPoint[];
  };
  exportedStep: {
    id: string;
    searchName: string;
    displayName: string;
    estimatedSize: number;
  };
  exportedStrategyName: string;
}

const ABSENT: EdaRecording = {
  siteId: "",
  datasetId: "",
  studyId: "",
  analysisId: "",
  studyTitle: "",
  analysisUrl: "",
  studyRow: {},
  countsUnfiltered: [],
  countsFebrile: [],
  febrileFilter: { entityId: "", variableId: "", type: "", stringSet: [] },
  febrileSummary: "",
  febrileDistribution: { labels: [], values: [], subsetSize: 0, numVarValues: 0 },
  compute: { groupA: [], groupB: [] },
  comparisonSentence: "",
  volcano: {
    chart: "",
    effectSizeLabel: "",
    effectSizeThreshold: 0,
    significanceThreshold: 0,
    effectDirection: "",
    totalPoints: 0,
    retainedPoints: 0,
    retainedPointIds: [],
    points: [],
  },
  exportedStep: { id: "", searchName: "", displayName: "", estimatedSize: 0 },
  exportedStrategyName: "",
};

const RECORDED = existsSync(EDA_RECORDING_FILE);
const EDA: EdaRecording = RECORDED
  ? (JSON.parse(readFileSync(EDA_RECORDING_FILE, "utf8")) as EdaRecording)
  : ABSENT;

export const EDA_RECORDING_MISSING = !RECORDED;

const EDA_LIVE = process.env["PATHFINDER_EDA_LIVE"] === "1";

export const SITE_ID = EDA.siteId;
export const DATASET_ID = EDA.datasetId;
export const STUDY_TITLE = EDA.studyTitle;
export const ANALYSIS_URL = EDA.analysisUrl;
export const STUDY_ROW = EDA.studyRow;
export const FEBRILE_FILTER = EDA.febrileFilter;
export const FEBRILE_SUMMARY = EDA.febrileSummary;
export const COMPARISON_SENTENCE = EDA.comparisonSentence;

const number = (value: number): string => value.toLocaleString("en-US");

export function countLine(count: EntityCount): string {
  return `${number(count.count)} of ${number(count.unfilteredCount)} ${count.entityDisplayName}`;
}

export const FEBRILE_COUNTS = EDA.countsFebrile;
export const FEBRILE_VALUE = EDA.febrileFilter.stringSet[0] ?? "";
export const SUBSET_FIRST_BIN = `${EDA.febrileDistribution.labels[0] ?? ""} ${String(EDA.febrileDistribution.values[0] ?? "")}`;
export const SUBSET_COVERAGE = `${number(EDA.febrileDistribution.numVarValues)} of ${number(EDA.febrileDistribution.subsetSize)} records have a value`;

const selected = EDA.volcano.retainedPointIds;
const dropped = EDA.volcano.points.filter((point) => point.pValue === null).length;
export const VOLCANO_SELECTED = selected;
export const VOLCANO_SELECTION = `${number(selected.length)} ${selected.length === 1 ? "gene" : "genes"} selected at these thresholds - ${number(EDA.volcano.retainedPoints)} of ${number(EDA.volcano.totalPoints)} retained by the comparison`;
export const VOLCANO_DROPPED =
  dropped === 1
    ? "1 point without a p-value was not plotted"
    : `${String(dropped)} points without a p-value were not plotted`;
export const EXPORTED_SIZE = number(EDA.exportedStep.estimatedSize);

export function analysisState(overrides: Record<string, unknown> = {}) {
  return {
    siteId: EDA.siteId,
    datasetId: EDA.datasetId,
    studyId: EDA.studyId,
    analysisId: EDA.analysisId,
    revision: 0,
    studyDisplayName: EDA.studyTitle,
    displayName: "Unsaved analysis",
    numFilters: 0,
    numComputations: 0,
    filters: [],
    filterSummaries: [],
    entityCounts: EDA.countsUnfiltered,
    canExportRows: true,
    analysisUrl: EDA.analysisUrl,
    ...overrides,
  };
}

export const FILTERED_ANALYSIS = analysisState({
  revision: 1,
  numFilters: 1,
  filters: [EDA.febrileFilter],
  filterSummaries: [EDA.febrileSummary],
  entityCounts: EDA.countsFebrile,
});

export const COMPARED_ANALYSIS = analysisState({
  revision: 2,
  numFilters: 1,
  numComputations: 1,
  filters: [EDA.febrileFilter],
  filterSummaries: [EDA.febrileSummary],
  entityCounts: EDA.countsFebrile,
  compute: EDA.compute,
});

export const VOLCANO_VIZ = {
  datasetId: EDA.datasetId,
  analysisId: EDA.analysisId,
  ...EDA.volcano,
};

export const VOLCANO_RESPONSE = {
  ...EDA.volcano,
  comparison: { groupA: EDA.compute.groupA, groupB: EDA.compute.groupB },
};

export const SUBSET_PREVIEW = {
  datasetId: EDA.datasetId,
  analysisId: EDA.analysisId,
  entityCounts: EDA.countsFebrile,
  distribution: EDA.febrileDistribution,
  distributionNote: null,
};

export const EXPORTED_STEP = EDA.exportedStep;

export function exportedStrategy(conversationId: string) {
  return {
    id: conversationId,
    name: EDA.exportedStrategyName,
    siteId: EDA.siteId,
    recordType: "transcript",
    rootStepId: EDA.exportedStep.id,
    isSaved: false,
    steps: [EDA.exportedStep],
    createdAt: "2026-08-28T00:00:00Z",
    updatedAt: "2026-08-28T00:00:00Z",
  };
}

export function edaJson(body: unknown) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

export async function routeEdaReads(page: Page): Promise<void> {
  if (EDA_LIVE) return;
  await page.route("**/api/v1/eda/studies?*", (route) =>
    route.fulfill(edaJson({ studies: [EDA.studyRow] })),
  );
  await page.route("**/api/v1/eda/viz?*", (route) =>
    route.fulfill(edaJson(VOLCANO_RESPONSE)),
  );
}
