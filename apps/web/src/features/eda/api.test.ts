/**
 * @vitest-environment jsdom
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import {
  edaViz,
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
              sites: ["plasmodb"],
              notHere: null,
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
    expect(result.studies[0]?.sites).toEqual(["plasmodb"]);
  });
});

describe("edaViz", () => {
  it("names the conversation, sends no cut, and keeps a point with no p-value", async () => {
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
      chart: "volcano",
    });
    expect(seenUrl).toContain("conversationId=1f1a4b0c-0f6b-4a53-9f9e-9d1f4e5b6c7d");
    expect(body).toEqual({ chart: "volcano" });
    expect(result.retainedPoints).toBe(1543);
    expect(result.points[1]?.pValue).toBe(null);
    expect(result.comparison).toEqual({ groupA: ["normal"], groupB: ["febrile"] });
  });
});

describe("getConversationEda", () => {
  it("returns the conversation's analysis state with its comparison", async () => {
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
            compute: {
              method: "DESeq",
              identifierVariable: "Gene",
              valueVariable: "Antisense Count",
              comparatorVariable: "temperature_condition",
              groupA: ["normal"],
              groupB: ["febrile"],
            },
          },
        }),
      ),
    );
    const result = await getConversationEda("conv-1");
    expect(result.analysis?.analysisId).toBe("a-1");
    expect(result.analysis?.revision).toBe(4);
    expect(result.analysis?.numFilters).toBe(1);
    expect(result.analysis?.entityCounts[0]?.unfilteredCount).toBe(12);
    expect(result.analysis?.compute?.comparatorVariable).toBe("temperature_condition");
  });

  it("returns a null analysis for a conversation with none open", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ analysis: null }),
      ),
    );
    const result = await getConversationEda("conv-1");
    expect(result.analysis).toBe(null);
  });

  it("refuses a body that omits the analysis key", async () => {
    server.use(
      http.get(`${BASE}/api/v1/conversations/conv-1/eda`, () => HttpResponse.json({})),
    );
    await expect(getConversationEda("conv-1")).rejects.toThrow(SchemaValidationError);
    await expect(getConversationEda("conv-1")).rejects.toThrow(/validation failed/);
  });
});

describe("patchConversationEda", () => {
  it("sends the bind action and returns the new analysis state", async () => {
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
            revision: 1,
            studyDisplayName: "Heat shock response",
            displayName: "EDA analysis",
            numFilters: 0,
            numComputations: 0,
            filters: [],
            filterSummaries: [],
            entityCounts: [],
            canExportRows: true,
          },
          step: null,
        });
      }),
    );
    const result = await patchConversationEda("conv-1", {
      action: "bind",
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
    });
    expect(body).toEqual({
      action: "bind",
      siteId: "plasmodb",
      datasetId: "DS_e973eadd57",
    });
    expect(result.analysis?.revision).toBe(1);
  });

  it("sends unbind with no other field and accepts a null analysis", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ analysis: null, step: null });
      }),
    );
    const result = await patchConversationEda("conv-1", { action: "unbind" });
    expect(body).toEqual({ action: "unbind" });
    expect(result.analysis).toBe(null);
  });

  it("sends the export's source and no cut", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ analysis: null, step: { rootStepId: 132 } });
      }),
    );
    await patchConversationEda("conv-1", { action: "export-step", source: "volcano" });
    expect(body).toEqual({ action: "export-step", source: "volcano" });
  });

  it("refuses an envelope that omits the analysis key", async () => {
    server.use(
      http.patch(`${BASE}/api/v1/conversations/conv-1/eda`, () =>
        HttpResponse.json({ step: null }),
      ),
    );
    await expect(patchConversationEda("conv-1", { action: "unbind" })).rejects.toThrow(
      /validation failed/,
    );
  });
});
