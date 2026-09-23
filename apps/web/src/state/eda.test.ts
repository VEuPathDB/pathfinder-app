import { beforeEach, describe, expect, it } from "vitest";

import {
  isEdaJobComplete,
  isEdaJobFailed,
  isEdaJobRunning,
  parseAnalysisFilters,
  selectEffectiveFilters,
  useEdaStore,
} from "./eda";

const FEBRILE = {
  entityId: "ENT_8151325d",
  variableId: "VAR_081ab087",
  type: "stringSet",
  stringSet: ["febrile"],
};

const ANALYSIS_STATE = {
  siteId: "plasmodb",
  datasetId: "DS_e973eadd57",
  studyId: "STUDY_e973eadd57",
  analysisId: "a-1",
  revision: 2,
  studyDisplayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
  displayName: "Febrile samples",
  numFilters: 1,
  numComputations: 0,
  filters: [FEBRILE],
  filterSummaries: ["temperature_condition is febrile"],
  entityCounts: [
    {
      entityId: "ENT_8151325d",
      entityDisplayName: "Sample",
      count: 6,
      unfilteredCount: 12,
    },
  ],
  canExportRows: true,
};

const SUBSET_PREVIEW = {
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

const VIZ = {
  datasetId: "DS_e973eadd57",
  analysisId: "a-1",
  chart: "volcano" as const,
  effectSizeLabel: "log2(Fold Change)",
  effectSizeThreshold: 2,
  significanceThreshold: 0.01,
  effectDirection: "upOnly" as const,
  totalPoints: 5511,
  retainedPoints: 1543,
  points: [
    {
      pointId: "PF3D7_0100200",
      effectSize: 3.94437533216012,
      pValue: 1.95781599815607e-5,
      adjustedPValue: 0.000137772236907279,
      retained: true,
    },
  ],
};

beforeEach(() => {
  useEdaStore.getState().reset();
});

describe("parseAnalysisFilters", () => {
  it("parses a wire filter the generated schema recognises", () => {
    const parsed = parseAnalysisFilters([FEBRILE]);
    expect(parsed.filters).toHaveLength(1);
    expect(parsed.unparsedCount).toBe(0);
  });

  it("drops an entry the schema rejects and counts it", () => {
    const parsed = parseAnalysisFilters([FEBRILE, { type: "notAFilter" }, 7]);
    expect(parsed.filters).toHaveLength(1);
    expect(parsed.unparsedCount).toBe(2);
  });

  it("returns an empty result for an empty array", () => {
    expect(parseAnalysisFilters([])).toEqual({ filters: [], unparsedCount: 0 });
  });
});

describe("useEdaStore.applyAnalysisState", () => {
  it("binds the conversation to the analysis the part names", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    expect(useEdaStore.getState().binding).toEqual({
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
      analysisId: "a-1",
    });
  });

  it("keeps the study title and the analysis name apart", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    const analysis = useEdaStore.getState().analysis;
    expect(analysis?.studyDisplayName).toBe(
      "Heat shock response in sensitive mutants (LRR5, DHC)",
    );
    expect(analysis?.displayName).toBe("Febrile samples");
  });

  it("stores the parsed filters, the summaries and the counts", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    const analysis = useEdaStore.getState().analysis;
    expect(analysis?.filters).toHaveLength(1);
    expect(analysis?.unparsedFilterCount).toBe(0);
    expect(analysis?.filterSummaries).toEqual(["temperature_condition is febrile"]);
    expect(analysis?.entityCounts[0]?.unfilteredCount).toBe(12);
    expect(analysis?.canExportRows).toBe(true);
  });

  it("keeps the site explorer link the part names", () => {
    const analysisUrl =
      "https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/a-1";
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, analysisUrl });
    expect(useEdaStore.getState().analysis?.analysisUrl).toBe(analysisUrl);
  });

  it("holds no site link for a part that names none", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    expect(useEdaStore.getState().analysis?.analysisUrl).toBe(null);
  });

  it("counts a filter the generated schema cannot parse instead of hiding it", () => {
    useEdaStore
      .getState()
      .applyAnalysisState({ ...ANALYSIS_STATE, filters: [FEBRILE, { junk: 1 }] });
    const analysis = useEdaStore.getState().analysis;
    expect(analysis?.filters).toHaveLength(1);
    expect(analysis?.unparsedFilterCount).toBe(1);
  });

  it("clears an optimistic local edit, because the server part is the truth", () => {
    useEdaStore.getState().setLocalFilters([]);
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    expect(useEdaStore.getState().localFilters).toBe(null);
  });

  it("ignores a part whose revision is older than the state it holds", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore
      .getState()
      .applyAnalysisState({ ...ANALYSIS_STATE, revision: 1, displayName: "Stale" });
    expect(useEdaStore.getState().analysis?.displayName).toBe("Febrile samples");
  });

  it("keeps an optimistic local edit when it ignores an older part", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().setLocalFilters([]);
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, revision: 1 });
    expect(useEdaStore.getState().localFilters).toEqual([]);
  });

  it("accepts an equal revision, because a re-emit carries the same document", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore
      .getState()
      .applyAnalysisState({ ...ANALYSIS_STATE, displayName: "Renamed" });
    expect(useEdaStore.getState().analysis?.displayName).toBe("Renamed");
  });

  it("replaces wholesale when the analysis id changes, whatever the revision", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore
      .getState()
      .applyAnalysisState({ ...ANALYSIS_STATE, analysisId: "a-2", revision: 0 });
    expect(useEdaStore.getState().analysis?.analysisId).toBe("a-2");
    expect(useEdaStore.getState().binding?.analysisId).toBe("a-2");
  });

  it("takes the last write when neither side carries a revision", () => {
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, revision: null });
    useEdaStore
      .getState()
      .applyAnalysisState({ ...ANALYSIS_STATE, revision: null, displayName: "Later" });
    expect(useEdaStore.getState().analysis?.displayName).toBe("Later");
  });

  it("drops the previous analysis preview, plots and jobs on a new analysis", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applySubsetPreview(SUBSET_PREVIEW);
    useEdaStore.getState().applyViz(VIZ);
    useEdaStore.getState().applyJob({
      jobId: "db04204e5386396e1ca2cb78469ab6fb",
      taskId: null,
      appName: "differentialexpression",
      status: "complete",
    });
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, analysisId: "a-2" });
    const state = useEdaStore.getState();
    expect(state.subsetPreview).toBe(null);
    expect(state.viz).toEqual({});
    expect(state.jobs).toEqual({});
    expect(state.volcanoThresholds).toEqual({
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      direction: "upAndDown",
    });
  });
});

describe("useEdaStore.applySubsetPreview", () => {
  it("keeps the latest preview with its counts and distribution", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applySubsetPreview(SUBSET_PREVIEW);
    const preview = useEdaStore.getState().subsetPreview;
    expect(preview?.entityCounts[0]?.count).toBe(6);
    expect(preview?.distribution?.values).toEqual([6, 6]);
  });

  it("ignores a preview for another analysis", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore
      .getState()
      .applySubsetPreview({ ...SUBSET_PREVIEW, analysisId: "other" });
    expect(useEdaStore.getState().subsetPreview).toBe(null);
  });
});

describe("useEdaStore.applyViz", () => {
  it("keys viz payloads by their chart", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz(VIZ);
    expect(useEdaStore.getState().viz["volcano"]?.retainedPoints).toBe(1543);
  });

  it("replaces the payload for the same chart", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz(VIZ);
    useEdaStore.getState().applyViz({ ...VIZ, retainedPoints: 1200 });
    expect(useEdaStore.getState().viz["volcano"]?.retainedPoints).toBe(1200);
  });

  it("ignores a plot for another analysis", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz({ ...VIZ, analysisId: "other" });
    expect(useEdaStore.getState().viz).toEqual({});
  });

  it("adopts the thresholds the backend used, so the chart agrees with retained", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz(VIZ);
    expect(useEdaStore.getState().volcanoThresholds).toEqual({
      effectSizeThreshold: 2,
      significanceThreshold: 0.01,
      direction: "upOnly",
    });
  });

  it("leaves a researcher's own thresholds alone", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().setVolcanoThresholds({
      effectSizeThreshold: 5,
      significanceThreshold: 0.001,
      direction: "downOnly",
    });
    useEdaStore.getState().applyViz(VIZ);
    expect(useEdaStore.getState().volcanoThresholds.effectSizeThreshold).toBe(5);
  });

  it("does not adopt a partial threshold set", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz({ ...VIZ, significanceThreshold: null });
    expect(useEdaStore.getState().volcanoThresholds).toEqual({
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      direction: "upAndDown",
    });
  });
});

describe("useEdaStore jobs and thresholds", () => {
  it("tracks a compute job by its id", () => {
    useEdaStore.getState().applyJob({
      jobId: "db04204e5386396e1ca2cb78469ab6fb",
      taskId: null,
      appName: "differentialexpression",
      status: "in-progress",
    });
    expect(
      useEdaStore.getState().jobs["db04204e5386396e1ca2cb78469ab6fb"]?.status,
    ).toBe("in-progress");
  });

  it("defaults the volcano thresholds to the upstream defaults", () => {
    expect(useEdaStore.getState().volcanoThresholds).toEqual({
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      direction: "upAndDown",
    });
  });

  it("resets every slice", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz(VIZ);
    useEdaStore.getState().reset();
    const state = useEdaStore.getState();
    expect(state.analysis).toBe(null);
    expect(state.binding).toBe(null);
    expect(state.viz).toEqual({});
    expect(state.jobs).toEqual({});
  });
});

describe("selectEffectiveFilters", () => {
  it("prefers the optimistic local edit over the server document", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().setLocalFilters([]);
    expect(selectEffectiveFilters(useEdaStore.getState())).toEqual([]);
  });

  it("falls back to the server document once the local edit is dropped", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().setLocalFilters([]);
    useEdaStore.getState().setLocalFilters(null);
    expect(selectEffectiveFilters(useEdaStore.getState())).toHaveLength(1);
  });

  it("is an empty array when nothing is bound", () => {
    expect(selectEffectiveFilters(useEdaStore.getState())).toEqual([]);
  });
});

describe("job status predicates", () => {
  const job = {
    jobId: "j",
    taskId: null,
    appName: "differentialexpression",
    status: "queued",
  };

  it("calls queued and in-progress running", () => {
    expect(isEdaJobRunning({ ...job, status: "queued" })).toBe(true);
    expect(isEdaJobRunning({ ...job, status: "in-progress" })).toBe(true);
  });

  it("calls complete complete and nothing else", () => {
    expect(isEdaJobComplete({ ...job, status: "complete" })).toBe(true);
    expect(isEdaJobComplete({ ...job, status: "expired" })).toBe(false);
  });

  it("calls failed failed and nothing else", () => {
    expect(isEdaJobFailed({ ...job, status: "failed" })).toBe(true);
    expect(isEdaJobFailed({ ...job, status: "no-such-job" })).toBe(false);
  });

  it("calls no-such-job and expired neither running nor complete", () => {
    expect(isEdaJobRunning({ ...job, status: "no-such-job" })).toBe(false);
    expect(isEdaJobComplete({ ...job, status: "no-such-job" })).toBe(false);
    expect(isEdaJobRunning({ ...job, status: "expired" })).toBe(false);
  });
});
