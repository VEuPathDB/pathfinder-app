import { test, expect } from "../fixtures/test";
import { signInAsWdkAccount } from "../fixtures/wdk-account";

// GO:0004672-curated P. falciparum 3D7 protein kinases (pulled from live WDK).
const KINASE_IDS = [
  "PF3D7_0102600",
  "PF3D7_0107600",
  "PF3D7_0203100",
  "PF3D7_0211700",
  "PF3D7_0213400",
  "PF3D7_0214600",
  "PF3D7_0217500",
  "PF3D7_0301200",
  "PF3D7_0302100",
  "PF3D7_0309200",
  "PF3D7_0310100",
  "PF3D7_0311400",
  "PF3D7_0312400",
  "PF3D7_0317200",
  "PF3D7_0321400",
  "PF3D7_0415300",
  "PF3D7_0417800",
  "PF3D7_0420100",
  "PF3D7_0424500",
  "PF3D7_0424700",
  "PF3D7_0500900",
  "PF3D7_0503500",
  "PF3D7_0525900",
  "PF3D7_0605300",
  "PF3D7_0610600",
  "PF3D7_0615500",
  "PF3D7_0623800",
  "PF3D7_0628200",
  "PF3D7_0704500",
  "PF3D7_0708300",
  "PF3D7_0715300",
  "PF3D7_0717500",
  "PF3D7_0718100",
  "PF3D7_0719200",
  "PF3D7_0724000",
  "PF3D7_0724600",
  "PF3D7_0726200",
  "PF3D7_0805700",
  "PF3D7_0821100",
  "PF3D7_0823000",
  "PF3D7_0902000",
  "PF3D7_0926000",
  "PF3D7_0928800",
  "PF3D7_0934800",
  "PF3D7_1014400",
  "PF3D7_1016400",
  "PF3D7_1039000",
  "PF3D7_1103700",
  "PF3D7_1106800",
  "PF3D7_1108400",
  "PF3D7_1112100",
  "PF3D7_1113900",
  "PF3D7_1114700",
  "PF3D7_1121300",
  "PF3D7_1122800",
  "PF3D7_1136500",
  "PF3D7_1145200",
  "PF3D7_1148000",
  "PF3D7_1201600",
  "PF3D7_1223100",
  "PF3D7_1228300",
  "PF3D7_1230900",
  "PF3D7_1238900",
  "PF3D7_1241200",
  "PF3D7_1246900",
  "PF3D7_1305500",
  "PF3D7_1315100",
  "PF3D7_1321100",
  "PF3D7_1331000",
  "PF3D7_1337100",
  "PF3D7_1349300",
  "PF3D7_1356800",
  "PF3D7_1371700",
  "PF3D7_1423600",
  "PF3D7_1428500",
  "PF3D7_1431500",
  "PF3D7_1436600",
  "PF3D7_1444500",
  "PF3D7_1450000",
  "PF3D7_1454300",
  "PF3D7_1463700",
  "PF3D7_1474700",
];

interface EnrichTerm {
  termId: string;
  termName: string;
  geneCount: number;
  pValue: number;
}
interface EnrichResult {
  analysisType: string;
  terms: EnrichTerm[];
  totalGenesAnalyzed: number;
}

test.describe("Workbench enrichment", () => {
  test("create gene set + GO enrichment returns real kinase terms (real account)", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    const ctx = page.context().request;
    const csrf = { "X-Requested-With": "XMLHttpRequest" };
    await signInAsWdkAccount(ctx, "plasmodb");

    const created = await ctx.post("/api/v1/gene-sets", {
      data: {
        name: "kinase controls",
        siteId: "plasmodb",
        geneIds: KINASE_IDS,
        source: "paste",
      },
      headers: csrf,
    });
    expect(created.status(), await created.text()).toBe(201);
    const geneSetId = ((await created.json()) as { id: string }).id;

    try {
      const enriched = await ctx.post(`/api/v1/gene-sets/${geneSetId}/enrich`, {
        data: { enrichmentTypes: ["go_process"] },
        headers: csrf,
      });
      expect(enriched.ok(), await enriched.text()).toBeTruthy();
      const results = (await enriched.json()) as EnrichResult[];

      const go = results.find((r) => r.analysisType === "go_process");
      expect(go).toBeDefined();
      expect(go!.totalGenesAnalyzed).toBeGreaterThanOrEqual(50);
      expect(go!.terms.length).toBeGreaterThanOrEqual(5);
      for (const term of go!.terms) {
        expect(term.termId).toMatch(/^GO:/);
        expect(term.termName.length).toBeGreaterThan(0);
        expect(term.pValue).toBeGreaterThanOrEqual(0);
      }
      expect(go!.terms.some((t) => /phosphorylat/i.test(t.termName))).toBeTruthy();
    } finally {
      await ctx
        .delete(`/api/v1/gene-sets/${geneSetId}`, { headers: csrf })
        .catch(() => undefined);
    }
  });
});
