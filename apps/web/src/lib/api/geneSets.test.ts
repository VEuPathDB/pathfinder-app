/**
 * @vitest-environment jsdom
 */
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../../../vitest.msw-setup";
import {
  deleteGeneSet,
  getGeneSetVdiPublication,
  listGeneSets,
  publishGeneSetToVdi,
} from "./geneSets";

const BASE = "http://localhost:3000/api/v1/gene-sets";
const GENE_SET_ID = "5b0c2f5e-3a51-4f7e-9d0c-0f4d3a1f2b61";
const VDI_ID = "soV5JEQEcF00p";
const DATASET_URL = `https://plasmodb.org/plasmo/app/workspace/datasets/${VDI_ID}`;

const KINASES = {
  id: GENE_SET_ID,
  name: "Kinases with a signal peptide",
  siteId: "plasmodb",
  geneIds: ["PF3D7_1133400", "PF3D7_0709000"],
  source: "strategy",
  geneCount: 2,
  membershipDigest: "0000000000000010",
  wdkStrategyId: 322476870,
  wdkStepId: 440299573,
  createdAt: "2026-09-05T00:00:00Z",
  stepCount: 2,
  vdiId: null,
};

describe("listGeneSets", () => {
  it("reads the researcher's sets on one site", async () => {
    let siteId: string | null = null;
    server.use(
      http.get(BASE, ({ request }) => {
        siteId = new URL(request.url).searchParams.get("siteId");
        return HttpResponse.json([KINASES]);
      }),
    );

    const sets = await listGeneSets("plasmodb");

    expect(siteId).toBe("plasmodb");
    expect(sets.map((set) => [set.id, set.geneCount])).toEqual([[GENE_SET_ID, 2]]);
  });

  it("sends no site filter when none is named", async () => {
    let query: string | null = null;
    server.use(
      http.get(BASE, ({ request }) => {
        query = new URL(request.url).search;
        return HttpResponse.json([]);
      }),
    );

    await expect(listGeneSets()).resolves.toEqual([]);
    expect(query).toBe("");
  });
});

describe("deleteGeneSet", () => {
  it("deletes one set by its id", async () => {
    let deleted: string | null = null;
    server.use(
      http.delete(`${BASE}/:id`, ({ params }) => {
        deleted = String(params["id"]);
        return HttpResponse.json({ ok: true });
      }),
    );

    await deleteGeneSet(GENE_SET_ID);

    expect(deleted).toBe(GENE_SET_ID);
  });

  it("rejects when the api refuses the delete", async () => {
    server.use(
      http.delete(`${BASE}/:id`, () =>
        HttpResponse.json(
          { title: "Not Found", status: 404, detail: "Gene set not found" },
          { status: 404 },
        ),
      ),
    );

    await expect(deleteGeneSet(GENE_SET_ID)).rejects.toThrow("Gene set not found");
  });
});

describe("publishGeneSetToVdi", () => {
  it("posts the name and the visibility and reads the created dataset", async () => {
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/${GENE_SET_ID}/vdi-publication`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { vdiId: VDI_ID, datasetUrl: DATASET_URL, siteId: "plasmodb", geneCount: 2 },
          { status: 201 },
        );
      }),
    );

    const published = await publishGeneSetToVdi(GENE_SET_ID, {
      name: "Kinases with a signal peptide",
      visibility: "private",
    });

    expect(body).toEqual({
      name: "Kinases with a signal peptide",
      visibility: "private",
    });
    expect(published.vdiId).toBe(VDI_ID);
    expect(published.datasetUrl).toBe(DATASET_URL);
  });
});

describe("getGeneSetVdiPublication", () => {
  it("reads where a published set stands", async () => {
    server.use(
      http.get(`${BASE}/${GENE_SET_ID}/vdi-publication`, () =>
        HttpResponse.json({
          vdiId: VDI_ID,
          datasetUrl: DATASET_URL,
          siteId: "plasmodb",
          upload: "success",
          importStatus: "complete",
          installedTargets: ["PlasmoDB"],
          installed: true,
          isTerminal: true,
        }),
      ),
    );

    const status = await getGeneSetVdiPublication(GENE_SET_ID);

    expect(status.installedTargets).toEqual(["PlasmoDB"]);
    expect(status.isTerminal).toBe(true);
  });
});
