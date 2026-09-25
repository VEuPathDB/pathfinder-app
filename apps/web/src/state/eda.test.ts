import { beforeEach, describe, expect, it } from "vitest";

import { useEdaStore } from "./eda";

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

const COMPUTE = {
  method: "DESeq",
  identifierVariable: "Gene",
  valueVariable: "Antisense Count",
  comparatorVariable: "temperature_condition",
  groupA: ["normal"],
  groupB: ["febrile"],
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

  it("stores the filter sentences and the counts", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    const analysis = useEdaStore.getState().analysis;
    expect(analysis?.numFilters).toBe(1);
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

  it("keeps the comparison the analysis holds, named as the study names it", () => {
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, compute: COMPUTE });
    expect(useEdaStore.getState().analysis?.compute).toEqual(COMPUTE);
  });

  it("holds no comparison for a part that names none", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    expect(useEdaStore.getState().analysis?.compute).toBe(null);
  });

  it("drops a comparison the site removed from the analysis", () => {
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, compute: COMPUTE });
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, compute: null });
    expect(useEdaStore.getState().analysis?.compute).toBe(null);
  });

  it("ignores a part whose revision is older than the state it holds", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore
      .getState()
      .applyAnalysisState({ ...ANALYSIS_STATE, revision: 1, displayName: "Stale" });
    expect(useEdaStore.getState().analysis?.displayName).toBe("Febrile samples");
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

  it("drops the previous analysis plots on a new analysis", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz(VIZ);
    useEdaStore.getState().applyAnalysisState({ ...ANALYSIS_STATE, analysisId: "a-2" });
    const state = useEdaStore.getState();
    expect(state.viz).toEqual({});
    expect(state.volcanoThresholds).toEqual({
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      direction: "upAndDown",
    });
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

  it("takes the cut of the latest plot, because the analysis stores the cut", () => {
    useEdaStore.getState().applyAnalysisState(ANALYSIS_STATE);
    useEdaStore.getState().applyViz(VIZ);
    useEdaStore.getState().applyViz({
      ...VIZ,
      effectSizeThreshold: 1.5,
      significanceThreshold: 0.05,
      effectDirection: "downOnly",
    });
    expect(useEdaStore.getState().volcanoThresholds).toEqual({
      effectSizeThreshold: 1.5,
      significanceThreshold: 0.05,
      direction: "downOnly",
    });
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

describe("useEdaStore thresholds and reset", () => {
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
  });
});
