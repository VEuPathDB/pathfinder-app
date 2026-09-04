import { useState } from "react";
import type {
  EdaAnalysisState,
  EdaEntityCount,
  EdaSubsetPreview,
  EdaViz,
} from "@pathfinder/shared";
import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";
import { edaFilterSchema } from "@pathfinder/shared/generated/zod/edaFilterSchema";

import type { VolcanoThresholds } from "@/lib/components/charts/types";

import { createStore } from "./middleware";

interface EdaBinding {
  siteId: string;
  datasetId: string;
  analysisId: string;
}

interface EdaAnalysisSnapshot {
  analysisId: string;
  revision: number | null;
  siteId: string;
  datasetId: string;
  studyId: string;
  studyDisplayName: string;
  displayName: string;
  numFilters: number;
  numComputations: number;
  filters: EdaFilter[];
  unparsedFilterCount: number;
  filterSummaries: string[];
  entityCounts: EdaEntityCount[];
  canExportRows: boolean;
}

export interface EdaJobSnapshot {
  jobId: string;
  taskId: string | null;
  appName: string;
  status: string;
}

export function isEdaJobRunning(job: EdaJobSnapshot): boolean {
  return job.status === "queued" || job.status === "in-progress";
}

export function isEdaJobComplete(job: EdaJobSnapshot): boolean {
  return job.status === "complete";
}

export function isEdaJobFailed(job: EdaJobSnapshot): boolean {
  return job.status === "failed";
}

/** The shared models type an analysis's filters as JSON, so each entry is
 * validated here and an unrecognised one is counted, never hidden. */
export function parseAnalysisFilters(raw: readonly unknown[]): {
  filters: EdaFilter[];
  unparsedCount: number;
} {
  const filters: EdaFilter[] = [];
  let unparsedCount = 0;
  for (const entry of raw) {
    const parsed = edaFilterSchema.safeParse(entry);
    if (parsed.success) filters.push(parsed.data);
    else unparsedCount += 1;
  }
  return { filters, unparsedCount };
}

const DEFAULT_THRESHOLDS: VolcanoThresholds = {
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  direction: "upAndDown",
};

interface EdaSlice {
  binding: EdaBinding | null;
  analysis: EdaAnalysisSnapshot | null;
  subsetPreview: EdaSubsetPreview | null;
  viz: Record<string, EdaViz>;
  jobs: Record<string, EdaJobSnapshot>;
  localFilters: EdaFilter[] | null;
  volcanoThresholds: VolcanoThresholds;
  volcanoThresholdsEdited: boolean;
}

export interface EdaState extends EdaSlice {
  applyAnalysisState: (payload: EdaAnalysisState) => void;
  applySubsetPreview: (payload: EdaSubsetPreview) => void;
  applyViz: (payload: EdaViz) => void;
  applyJob: (job: EdaJobSnapshot) => void;
  setLocalFilters: (filters: EdaFilter[] | null) => void;
  setVolcanoThresholds: (thresholds: VolcanoThresholds) => void;
  reset: () => void;
}

const INITIAL: EdaSlice = {
  binding: null,
  analysis: null,
  subsetPreview: null,
  viz: {},
  jobs: {},
  localFilters: null,
  volcanoThresholds: DEFAULT_THRESHOLDS,
  volcanoThresholdsEdited: false,
};

/** A part supersedes the state it holds unless it names an older revision of
 * the same analysis. */
function supersedes(
  current: EdaAnalysisSnapshot | null,
  payload: EdaAnalysisState,
): boolean {
  if (current === null) return true;
  if (current.analysisId !== payload.analysisId) return true;
  if (current.revision === null || payload.revision === null) return true;
  return payload.revision >= current.revision;
}

function snapshotOf(payload: EdaAnalysisState): EdaAnalysisSnapshot {
  const { filters, unparsedCount } = parseAnalysisFilters(payload.filters);
  return {
    analysisId: payload.analysisId,
    revision: payload.revision,
    siteId: payload.siteId,
    datasetId: payload.datasetId,
    studyId: payload.studyId,
    studyDisplayName: payload.studyDisplayName,
    displayName: payload.displayName,
    numFilters: payload.numFilters,
    numComputations: payload.numComputations,
    filters,
    unparsedFilterCount: unparsedCount,
    filterSummaries: payload.filterSummaries,
    entityCounts: payload.entityCounts,
    canExportRows: payload.canExportRows,
  };
}

export const useEdaStore = createStore<EdaState>("EdaStore", (set) => ({
  ...INITIAL,

  applyAnalysisState: (payload) =>
    set((s) => {
      if (!supersedes(s.analysis, payload)) return s;
      const switched = s.analysis?.analysisId !== payload.analysisId;
      return {
        binding: {
          siteId: payload.siteId,
          datasetId: payload.datasetId,
          analysisId: payload.analysisId,
        },
        analysis: snapshotOf(payload),
        localFilters: null,
        ...(switched
          ? {
              subsetPreview: null,
              viz: {},
              jobs: {},
              volcanoThresholds: DEFAULT_THRESHOLDS,
              volcanoThresholdsEdited: false,
            }
          : {}),
      };
    }),

  applySubsetPreview: (payload) =>
    set((s) =>
      s.analysis?.analysisId === payload.analysisId ? { subsetPreview: payload } : s,
    ),

  applyViz: (payload) =>
    set((s) => {
      if (s.analysis?.analysisId !== payload.analysisId) return s;
      const effectSize = payload.effectSizeThreshold ?? null;
      const significance = payload.significanceThreshold ?? null;
      const direction = payload.effectDirection ?? null;
      const adopt =
        !s.volcanoThresholdsEdited &&
        effectSize !== null &&
        significance !== null &&
        direction !== null;
      return {
        viz: { ...s.viz, [payload.chart]: payload },
        ...(adopt
          ? {
              volcanoThresholds: {
                effectSizeThreshold: effectSize,
                significanceThreshold: significance,
                direction,
              },
            }
          : {}),
      };
    }),

  applyJob: (job) => set((s) => ({ jobs: { ...s.jobs, [job.jobId]: job } })),

  setLocalFilters: (filters) => set({ localFilters: filters }),

  setVolcanoThresholds: (thresholds) =>
    set({ volcanoThresholds: thresholds, volcanoThresholdsEdited: true }),

  reset: () => set({ ...INITIAL }),
}));

/** Filters the tab renders: the optimistic local edit while one is pending,
 * otherwise the server document. */
export function selectEffectiveFilters(state: EdaState): EdaFilter[] {
  return state.localFilters ?? state.analysis?.filters ?? [];
}

type EdaHydratablePart =
  | { kind: "analysis-state"; data: EdaAnalysisState }
  | { kind: "subset-preview"; data: EdaSubsetPreview }
  | { kind: "viz"; data: EdaViz };

/** Feed one rendered data part into the store so the tab and the thread show
 * the same analysis. */
export function useHydrateEdaPart(part: EdaHydratablePart): void {
  const [appliedData, setAppliedData] = useState<unknown>(null);
  if (appliedData !== part.data) {
    setAppliedData(part.data);
    queueMicrotask(() => {
      const store = useEdaStore.getState();
      if (part.kind === "analysis-state") store.applyAnalysisState(part.data);
      else if (part.kind === "subset-preview") store.applySubsetPreview(part.data);
      else store.applyViz(part.data);
    });
  }
}
