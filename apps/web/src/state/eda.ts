import { useState } from "react";
import type { EdaAnalysisState, EdaEntityCount, EdaViz } from "@pathfinder/shared";
import type { EdaComputeSummary } from "@pathfinder/shared/generated/types/EdaComputeSummary";

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
  filterSummaries: string[];
  entityCounts: EdaEntityCount[];
  canExportRows: boolean;
  analysisUrl: string | null;
  compute: EdaComputeSummary | null;
}

const DEFAULT_THRESHOLDS: VolcanoThresholds = {
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  direction: "upAndDown",
};

interface EdaSlice {
  binding: EdaBinding | null;
  analysis: EdaAnalysisSnapshot | null;
  viz: Record<string, EdaViz>;
  volcanoThresholds: VolcanoThresholds;
}

export interface EdaState extends EdaSlice {
  applyAnalysisState: (payload: EdaAnalysisState) => void;
  applyViz: (payload: EdaViz) => void;
  reset: () => void;
}

const INITIAL: EdaSlice = {
  binding: null,
  analysis: null,
  viz: {},
  volcanoThresholds: DEFAULT_THRESHOLDS,
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
    filterSummaries: payload.filterSummaries,
    entityCounts: payload.entityCounts,
    canExportRows: payload.canExportRows,
    analysisUrl: payload.analysisUrl ?? null,
    compute: payload.compute ?? null,
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
        ...(switched ? { viz: {}, volcanoThresholds: DEFAULT_THRESHOLDS } : {}),
      };
    }),

  applyViz: (payload) =>
    set((s) => {
      if (s.analysis?.analysisId !== payload.analysisId) return s;
      const effectSize = payload.effectSizeThreshold ?? null;
      const significance = payload.significanceThreshold ?? null;
      const direction = payload.effectDirection ?? null;
      const adopt = effectSize !== null && significance !== null && direction !== null;
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

  reset: () => set({ ...INITIAL }),
}));

type EdaHydratablePart =
  { kind: "analysis-state"; data: EdaAnalysisState } | { kind: "viz"; data: EdaViz };

/** Feed one rendered data part into the store so the tab and the thread show
 * the same analysis. */
export function useHydrateEdaPart(part: EdaHydratablePart): void {
  const [appliedData, setAppliedData] = useState<unknown>(null);
  if (appliedData !== part.data) {
    setAppliedData(part.data);
    queueMicrotask(() => {
      const store = useEdaStore.getState();
      if (part.kind === "analysis-state") store.applyAnalysisState(part.data);
      else store.applyViz(part.data);
    });
  }
}
