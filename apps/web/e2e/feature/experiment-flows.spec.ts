import { test, expect } from "../fixtures/test";

/**
 * Feature: Phase 2a/2b chat flows — exploratory variant comparison, the
 * consult_user design-question gate, and attaching a gene-ID file to seed a
 * control set. Only the LLM is mocked; variant runs + gene-ID resolution hit
 * real WDK, and the control set is verified through the REST API.
 */
test.describe("Experiment chat flows", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage, sitePicker }) => {
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await sitePicker.expectCurrentSite("plasmodb");
  });

  test("compares two search variants and renders a comparison card", async ({
    chatPage,
  }) => {
    await chatPage.send("Please compare two search variants for me.");
    await chatPage.expectVariantComparison();
    // The card names each labelled variant.
    await expect(chatPage.variantComparison).toContainText(/kinase/i);
    await expect(chatPage.variantComparison).toContainText(/phosphatase/i);
    await chatPage.expectIdle();
  });

  test("consult_user gates the turn on design answers, then resumes", async ({
    chatPage,
  }) => {
    await chatPage.send("Consult me before planning this strategy.");
    // The blocking design-question carousel appears before any build.
    await chatPage.answerConsultCarousel();
    await chatPage.expectIdle();
  });

  test("attaching a gene-ID file seeds a control set", async ({
    chatPage,
    apiClient,
  }) => {
    const csv = ["geneId,product", "PF3D7_0709000,CRT", "PF3D7_1133400,AMA1"].join(
      "\n",
    );
    await chatPage.attachGeneIdFile("controls.csv", csv);
    await chatPage.send("Use these genes as my positive controls.");
    await chatPage.expectAssistantMessage(/control set/i, { timeout: 90_000 });
    await chatPage.expectIdle();

    // The control set was persisted with the resolved positive IDs.
    const resp = await apiClient.get("/api/v1/control-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const sets = (await resp.json()) as Array<{
      name: string;
      positiveIds: string[];
    }>;
    const uploaded = sets.find((s) => s.name === "Controls from controls.csv");
    expect(uploaded).toBeTruthy();
    expect(uploaded?.positiveIds).toContain("PF3D7_0709000");
  });
});
