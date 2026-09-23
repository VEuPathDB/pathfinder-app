/**
 * @vitest-environment jsdom
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import {
  countEdaSubset,
  edaDistribution,
  edaViz,
  getEdaStudyDetail,
  patchConversationEda,
  getConversationEda,
  searchEdaStudies,
} from "./api";
import { SchemaValidationError } from "@/lib/api/http";

const BASE = "http://localhost:3000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("searchEdaStudies", () => {
  it("sends the query and the site and returns the study rows", async () => {
    let seenUrl = "";
    server.use(
      http.get(`${BASE}/api/v1/eda/studies`, ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({
          studies: [
            {
              datasetId: "DS_e973eadd57",
              studyId: "STUDY_e973eadd57",
              displayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
              shortDisplayName: "Heat shock",
              description: "Heat shock of LRR5 and DHC knockdown parasites.",
              sourceType: "curated",
              relevance: 0.82,
              canSubset: true,
              canExportRows: true,
            },
          ],
        });
      }),
    );
    const result = await searchEdaStudies("plasmodb", "heat shock");
    expect(seenUrl).toContain("q=heat+shock");
    expect(seenUrl).toContain("siteId=plasmodb");
    expect(result.studies[0]?.datasetId).toBe("DS_e973eadd57");
    expect(result.studies[0]?.canExportRows).toBe(true);
  });
});

describe("getEdaStudyDetail", () => {
  it("names the dataset in the path and the site in the query", async () => {
    let seenUrl = "";
    server.use(
      http.get(`${BASE}/api/v1/eda/studies/DS_e973eadd57`, ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({
          datasetId: "DS_e973eadd57",
          studyId: "STUDY_e973eadd57",
          displayName: "Heat shock response",
          entities: [],
          variables: [],
          geneEntityId: "ENT_fd574cd6",
          geneEntityProblem: null,
          canSubset: true,
          canExportRows: true,
        });
      }),
    );
    const result = await getEdaStudyDetail("plasmodb", "DS_e973eadd57");
    expect(seenUrl).toContain("siteId=plasmodb");
    expect(result.studyId).toBe("STUDY_e973eadd57");
    expect(result.geneEntityId).toBe("ENT_fd574cd6");
  });
});

describe("countEdaSubset", () => {
  it("posts one entity with its filters and returns both counts", async () => {
    let body: unknown = null;
    let seenUrl = "";
    server.use(
      http.post(`${BASE}/api/v1/eda/count`, async ({ request }) => {
        seenUrl = request.url;
        body = await request.json();
        return HttpResponse.json({
          entityId: "GENE_PHENOTYPE_DATA_ENTITY",
          count: 4011,
          unfilteredCount: 4279,
        });
      }),
    );
    const result = await countEdaSubset({
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
      entityId: "GENE_PHENOTYPE_DATA_ENTITY",
      filters: [
        {
          entityId: "GENE_PHENOTYPE_DATA_ENTITY",
          variableId: "VAR_035294d0",
          type: "stringSet",
          stringSet: ["P. berghei"],
        },
      ],
    });
    expect(seenUrl).toContain("siteId=plasmodb");
    expect(body).toEqual({
      datasetId: "DS_e973eadd57",
      entityId: "GENE_PHENOTYPE_DATA_ENTITY",
      filters: [
        {
          entityId: "GENE_PHENOTYPE_DATA_ENTITY",
          variableId: "VAR_035294d0",
          type: "stringSet",
          stringSet: ["P. berghei"],
        },
      ],
    });
    expect(result.count).toBe(4011);
    expect(result.unfilteredCount).toBe(4279);
  });
});

describe("edaDistribution", () => {
  it("returns the settled distribution series with its statistics", async () => {
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/api/v1/eda/distribution`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          variableId: "EUPATH_0000047",
          variableDisplayName: "Hemoglobin",
          labels: ["[0.0,5.0)", "[5.0,10.0)", "[10.0,15.0)"],
          values: [13, 3254, 31990],
          subsetSize: 48721,
          numVarValues: 36570,
          numMissingCases: 12151,
          isMultiValued: false,
        });
      }),
    );
    const result = await edaDistribution({
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
      entityId: "ENT_8151325d",
      variableId: "EUPATH_0000047",
      filters: [],
    });
    expect(body).toEqual({
      datasetId: "DS_e973eadd57",
      entityId: "ENT_8151325d",
      variableId: "EUPATH_0000047",
      filters: [],
    });
    expect(result.values).toEqual([13, 3254, 31990]);
    expect(result.numMissingCases).toBe(12151);
  });
});

describe("edaViz", () => {
  it("names the conversation in the query and keeps a point with no p-value", async () => {
    let seenUrl = "";
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/api/v1/eda/viz`, async ({ request }) => {
        seenUrl = request.url;
        body = await request.json();
        return HttpResponse.json({
          chart: "volcano",
          effectSizeLabel: "log2(Fold Change)",
          effectSizeThreshold: 1,
          significanceThreshold: 0.05,
          effectDirection: "upAndDown",
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
            {
              pointId: "PF3D7_MIT04200",
              effectSize: -1.49447459261845,
              pValue: null,
              adjustedPValue: null,
              retained: false,
            },
          ],
          comparison: { groupA: ["normal"], groupB: ["febrile"] },
        });
      }),
    );
    const result = await edaViz({
      siteId: "plasmodb",
      conversationId: "1f1a4b0c-0f6b-4a53-9f9e-9d1f4e5b6c7d",
      datasetId: "DS_e973eadd57",
      chart: "volcano",
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      effectDirection: "upAndDown",
    });
    expect(seenUrl).toContain("conversationId=1f1a4b0c-0f6b-4a53-9f9e-9d1f4e5b6c7d");
    expect(body).toEqual({
      datasetId: "DS_e973eadd57",
      chart: "volcano",
      effectSizeThreshold: 1,
      significanceThreshold: 0.05,
      effectDirection: "upAndDown",
    });
    expect(result.retainedPoints).toBe(1543);
    expect(result.points[1]?.pValue).toBe(null);
    expect(result.comparison).toEqual({ groupA: ["normal"], groupB: ["febrile"] });
  });
});

describe("getConversationEda", () => {
  it("returns the thread's analysis state and the upstream descriptor", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({
          analysis: {
            siteId: "plasmodb",
            datasetId: "DS_e973eadd57",
            studyId: "STUDY_e973eadd57",
            analysisId: "a-1",
            revision: 4,
            studyDisplayName: "Heat shock response in sensitive mutants (LRR5, DHC)",
            displayName: "Febrile samples",
            numFilters: 1,
            numComputations: 0,
            filters: [
              {
                entityId: "ENT_8151325d",
                variableId: "VAR_081ab087",
                type: "stringSet",
                stringSet: ["febrile"],
              },
            ],
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
          },
          descriptor: { subset: { descriptor: [] } },
        }),
      ),
    );
    const result = await getConversationEda("conv-1");
    expect(result.analysis?.analysisId).toBe("a-1");
    expect(result.analysis?.revision).toBe(4);
    expect(result.analysis?.numFilters).toBe(1);
    expect(result.analysis?.entityCounts[0]?.unfilteredCount).toBe(12);
    expect(result.descriptor).toEqual({ subset: { descriptor: [] } });
  });

  it("returns a null analysis for a thread with none open", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: null, descriptor: null }),
      ),
    );
    const result = await getConversationEda("conv-1");
    expect(result.analysis).toBe(null);
    expect(result.descriptor).toBe(null);
  });

  it("refuses a body that omits the analysis key", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ descriptor: null }),
      ),
    );
    await expect(getConversationEda("conv-1")).rejects.toThrow(SchemaValidationError);
    await expect(getConversationEda("conv-1")).rejects.toThrow(/validation failed/);
  });
});

describe("patchConversationEda", () => {
  it("sends the set-filters action and returns the new analysis state", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          analysis: {
            siteId: "plasmodb",
            datasetId: "DS_e973eadd57",
            studyId: "STUDY_e973eadd57",
            analysisId: "a-1",
            revision: 4,
            studyDisplayName: "Heat shock response",
            displayName: "Febrile samples",
            numFilters: 0,
            numComputations: 0,
            filters: [],
            filterSummaries: [],
            entityCounts: [],
            canExportRows: true,
          },
          job: null,
          step: null,
        });
      }),
    );
    const result = await patchConversationEda("conv-1", {
      action: "set-filters",
      filters: [],
    });
    expect(body).toEqual({ action: "set-filters", filters: [] });
    expect(result.analysis?.revision).toBe(4);
  });

  it("sends unbind with no other field and accepts a null analysis", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ analysis: null, job: null, step: null });
      }),
    );
    const result = await patchConversationEda("conv-1", { action: "unbind" });
    expect(body).toEqual({ action: "unbind" });
    expect(result.analysis).toBe(null);
  });

  it("sends the export thresholds with the wire spelling effectDirection", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          analysis: null,
          job: null,
          step: { rootStepId: 132 },
        });
      }),
    );
    await patchConversationEda("conv-1", {
      action: "export-step",
      thresholds: {
        effectSizeThreshold: 1,
        significanceThreshold: 0.05,
        effectDirection: "upAndDown",
      },
    });
    expect(body).toEqual({
      action: "export-step",
      thresholds: {
        effectSizeThreshold: 1,
        significanceThreshold: 0.05,
        effectDirection: "upAndDown",
      },
    });
  });

  it("returns the job reference a run-compute answers with", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({
          analysis: null,
          job: {
            jobId: "db04204e5386396e1ca2cb78469ab6fb",
            taskId: null,
            appName: "differentialexpression",
            status: "in-progress",
          },
          step: null,
        }),
      ),
    );
    const result = await patchConversationEda("conv-1", {
      action: "run-compute",
      computation: {
        type: "differentialexpression",
        configuration: {
          identifierVariable: {
            entityId: "ENT_fd574cd6",
            variableId: "VEUPATHDB_GENE_ID",
          },
          valueVariable: {
            entityId: "ENT_fd574cd6",
            variableId: "SEQUENCE_READ_COUNT_SENSE",
          },
          comparator: {
            variable: { entityId: "ENT_8151325d", variableId: "VAR_081ab087" },
            groupA: [{ label: "normal" }],
            groupB: [{ label: "febrile" }],
          },
          differentialExpressionMethod: "DESeq",
          pValueFloor: "1e-200",
        },
      },
    });
    expect(result.job?.taskId ?? null).toBe(null);
    expect(result.job?.status).toBe("in-progress");
  });

  it("refuses an envelope that omits the analysis key", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ job: null, step: null }),
      ),
    );
    await expect(patchConversationEda("conv-1", { action: "unbind" })).rejects.toThrow(
      /validation failed/,
    );
  });
});
