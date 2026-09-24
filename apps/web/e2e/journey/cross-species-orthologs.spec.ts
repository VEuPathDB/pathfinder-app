import { test, expect } from "../fixtures/a11y";

/** The set the mock model saves when a message asks for one "as a gene set". */
const SAVED_SET = "mock gene set";
const SAVED_IDS = ["PF3D7_0709000", "PF3D7_1133400"];

interface GeneSetRow {
  id: string;
  name: string;
  siteId: string;
  geneCount: number;
}

/**
 * Journey: Cross-Species Ortholog Comparison, PlasmoDB then ToxoDB.
 *
 * Real WDK API, real DB. Only the LLM is mocked.
 *
 * Flow: PlasmoDB chat, a gene set saved from the chat and read back through
 * the API, a switch to ToxoDB whose list does not carry it, and a return to
 * PlasmoDB where the set is intact.
 */
test.describe("Cross-Species Orthologs Journey", () => {
  test("a gene set saved on one site stays on that site", async ({
    chatPage,
    page,
    apiClient,
    sitePicker,
  }) => {
    const setsOn = async (siteId: string): Promise<GeneSetRow[]> => {
      const resp = await apiClient.get(`/api/v1/gene-sets?siteId=${siteId}`);
      expect(resp.ok()).toBeTruthy();
      return (await resp.json()) as GeneSetRow[];
    };

    // ── Phase 1: PlasmoDB, chat and a saved gene set ─────────────

    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");

    await chatPage.send(
      "I'm comparing drug resistance genes across Plasmodium and Toxoplasma",
    );
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    await chatPage.send(`Save ${SAVED_IDS.join(" and ")} as a gene set`);
    await expect(page.getByTestId("data-gene-set")).toContainText(SAVED_SET, {
      timeout: 90_000,
    });
    await chatPage.expectIdle();

    const plasmoSets = await setsOn("plasmodb");
    const saved = plasmoSets.find((gs) => gs.name === SAVED_SET);
    expect(saved?.siteId).toBe("plasmodb");
    expect(saved?.geneCount).toBe(SAVED_IDS.length);

    // ── Phase 2: ToxoDB does not carry the PlasmoDB set ──────────

    await sitePicker.selectSite("toxodb");
    await sitePicker.expectCurrentSite("toxodb");

    await page.goto("/toxodb/conversation");
    await chatPage.send(
      "Now looking at T. gondii invasion proteins for cross-species comparison",
    );
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    const toxoSets = await setsOn("toxodb");
    expect(toxoSets.map((gs) => gs.id)).not.toContain(saved?.id);

    // ── Phase 3: back on PlasmoDB, the set is intact ─────────────

    await sitePicker.selectSite("plasmodb");
    await sitePicker.expectCurrentSite("plasmodb");

    const again = await setsOn("plasmodb");
    const intact = again.find((gs) => gs.id === saved?.id);
    expect(intact?.geneCount).toBe(SAVED_IDS.length);
  });
});
