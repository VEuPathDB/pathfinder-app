import { describe, expect, it } from "vitest";
import { edaAnalysisStateSchema } from "@pathfinder/shared/generated/zod/edaAnalysisStateSchema";
import { edaSubsetPreviewPartSchema } from "@pathfinder/shared/generated/zod/edaSubsetPreviewPartSchema";
import { edaVizPartSchema } from "@pathfinder/shared/generated/zod/edaVizPartSchema";

import { dataPartComponents } from "./contentComponents";
import { edaDataPartComponents } from "./edaDataParts";

const EDA_KINDS = [
  "data-eda.analysis-state",
  "data-eda.subset-preview",
  "data-eda.viz",
] as const;

describe("eda data parts", () => {
  it("registers a renderer for every eda kind", () => {
    for (const kind of EDA_KINDS) {
      expect(typeof edaDataPartComponents[kind]).toBe("function");
    }
  });

  it("is merged into the composed map", () => {
    for (const kind of EDA_KINDS) {
      expect(dataPartComponents[kind]).toBe(edaDataPartComponents[kind]);
    }
  });

  it("adds no kind the composed map does not carry", () => {
    expect(Object.keys(edaDataPartComponents).sort()).toEqual([...EDA_KINDS].sort());
  });
});

describe("eda zod schemas", () => {
  it("accepts an analysis-state payload the backend emits", () => {
    const parsed = edaAnalysisStateSchema.safeParse({
      siteId: "plasmodb",
      datasetId: "DS_53f554ec6a",
      studyId: "STUDY_53f554ec6a",
      analysisId: "t4fszEJ",
      revision: 1,
      studyDisplayName: "Rodent malaria phenotypes",
      displayName: "berghei subset",
      numFilters: 1,
      numComputations: 0,
      filters: [],
      filterSummaries: ["Species is one of P. berghei"],
      entityCounts: [],
      canExportRows: true,
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects a payload that omits a field the producer always fills", () => {
    const parsed = edaAnalysisStateSchema.safeParse({
      siteId: "plasmodb",
      datasetId: "DS_53f554ec6a",
      studyId: "STUDY_53f554ec6a",
      analysisId: "t4fszEJ",
    });
    expect(parsed.success).toBe(false);
  });

  it("rejects a payload missing the analysis id", () => {
    const parsed = edaAnalysisStateSchema.safeParse({
      siteId: "plasmodb",
      datasetId: "DS_x",
      studyId: "STUDY_x",
    });
    expect(parsed.success).toBe(false);
  });

  it("keeps the wire filter objects the union is not typed for", () => {
    const parsed = edaAnalysisStateSchema.safeParse({
      siteId: "plasmodb",
      datasetId: "DS_53f554ec6a",
      studyId: "STUDY_53f554ec6a",
      analysisId: "t4fszEJ",
      revision: 1,
      studyDisplayName: "Rodent malaria phenotypes",
      displayName: "berghei subset",
      numFilters: 1,
      numComputations: 0,
      filters: [
        {
          type: "stringSet",
          entityId: "GENE_PHENOTYPE_DATA_ENTITY",
          variableId: "VAR_035294d0",
          stringSet: ["P. berghei"],
        },
      ],
      filterSummaries: ["Species is one of P. berghei"],
      entityCounts: [],
      canExportRows: false,
    });
    expect(parsed.success).toBe(true);
    expect(parsed.data?.filters).toHaveLength(1);
  });

  it("accepts a subset preview whose distribution outruns the subset size", () => {
    const parsed = edaSubsetPreviewPartSchema.safeParse({
      datasetId: "DS_e973eadd57",
      analysisId: "t4fszEJ",
      entityCounts: [
        {
          entityId: "GENE_PHENOTYPE_DATA_ENTITY",
          entityDisplayName: "Gene phenotype",
          count: 4011,
          unfilteredCount: 4279,
        },
      ],
      distribution: {
        variableId: "VAR_035294d0",
        variableDisplayName: "Species",
        labels: ["P. berghei", "P. falciparum", "P. yoelii"],
        values: [4011, 4130, 268],
        subsetSize: 4279,
        numVarValues: 8409,
        numMissingCases: 0,
        isMultiValued: true,
      },
      distributionNote: null,
    });
    expect(parsed.success).toBe(true);
    expect(parsed.data?.entityCounts[0]?.count).toBe(4011);
  });

  it("accepts a volcano point with no p-value", () => {
    const parsed = edaVizPartSchema.safeParse({
      datasetId: "DS_e973eadd57",
      analysisId: "t4fszEJ",
      chart: "volcano",
      effectSizeLabel: "log2(Fold Change)",
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      effectDirection: "upAndDown",
      totalPoints: 5511,
      retainedPoints: 1543,
      retainedPointIds: [],
      points: [
        {
          pointId: "PF3D7_MIT04200",
          effectSize: -1.49447459261845,
          pValue: null,
          adjustedPValue: null,
          retained: false,
        },
      ],
    });
    expect(parsed.success).toBe(true);
    expect(parsed.data?.points[0]?.pValue).toBeNull();
  });

  it("refuses a plot that carries no retained id list", () => {
    const parsed = edaVizPartSchema.safeParse({
      datasetId: "DS_e973eadd57",
      analysisId: "t4fszEJ",
      chart: "volcano",
      effectSizeLabel: "log2(Fold Change)",
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      effectDirection: "upAndDown",
      totalPoints: 5511,
      retainedPoints: 1543,
      points: [],
    });
    expect(parsed.error?.issues.map((issue) => issue.path)).toEqual([
      ["retainedPointIds"],
    ]);
  });

  it("rejects a chart name no compute produces", () => {
    const parsed = edaVizPartSchema.safeParse({
      datasetId: "DS_e973eadd57",
      analysisId: "t4fszEJ",
      chart: "heatmap",
    });
    expect(parsed.success).toBe(false);
  });
});
