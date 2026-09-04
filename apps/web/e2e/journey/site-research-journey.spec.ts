import { test, expect } from "../fixtures/a11y";
import { MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";

/**
 * The researcher journey, once per component site: site switch, multi-round
 * chat, a strategy from the planning artifact, gene sets pasted from the
 * seeded ids, a real WDK enrichment run, and the set operation the site's
 * journey exercises. Real WDK, real Postgres, real worker; only the LLM is
 * mocked.
 */

interface ChatRound {
  readonly prompt: string;
  readonly reply: RegExp;
}

interface SetSpec {
  readonly name: string;
  /** "all" pastes every seeded gene id; "subset" pastes the first two. */
  readonly genes: "all" | "subset";
}

interface OperationSpec {
  readonly operation: "union" | "intersect" | "minus";
  /** The count the compose bar previews and the derived set carries. */
  readonly count: (full: number, subset: number) => number;
}

interface SiteJourney {
  readonly siteId: string;
  readonly title: string;
  readonly rounds: readonly ChatRound[];
  readonly sets: readonly SetSpec[];
  readonly operation?: OperationSpec;
  /** Query string of the conversations read that proves the strategy landed. */
  readonly conversationsQuery: string;
  readonly expectConversations: "ok" | "non-empty";
  readonly expectEnrichmentTabs: boolean;
  /** Panels that must be on screen for a paste-built set. */
  readonly panels?: readonly string[];
  /** The set whose row must carry `source: "paste"` in the API answer. */
  readonly expectPasteSource?: boolean;
  readonly followUp?: ChatRound;
}

const JOURNEYS: readonly SiteJourney[] = [
  {
    siteId: "plasmodb",
    title: "malaria drug resistance",
    rounds: [
      {
        prompt:
          "I'm investigating chloroquine resistance mechanisms in Plasmodium falciparum",
        reply: /have not built anything yet/i,
      },
      {
        prompt: "Can you help me find genes involved in drug resistance?",
        reply: /\[mock\].*Can you help/,
      },
    ],
    sets: [
      { name: "Drug Resistance Markers", genes: "all" },
      { name: "CRT & Kelch13", genes: "subset" },
    ],
    operation: { operation: "intersect", count: (_full, subset) => subset },
    conversationsQuery: "",
    expectConversations: "non-empty",
    expectEnrichmentTabs: true,
    followUp: {
      prompt: "Based on the enrichment results, what pathways should I investigate?",
      reply: /\[mock\].*enrichment/i,
    },
  },
  {
    siteId: "toxodb",
    title: "toxoplasma host invasion",
    rounds: [
      {
        prompt: "I'm studying host cell invasion mechanisms in Toxoplasma gondii",
        reply: /\[mock\]/,
      },
      {
        prompt: "What micronemal and rhoptry proteins are involved in attachment?",
        reply: /\[mock\].*micronemal/i,
      },
    ],
    sets: [
      { name: "Invasion Machinery", genes: "all" },
      { name: "Rhoptry Subset", genes: "subset" },
    ],
    operation: { operation: "union", count: (full) => full },
    conversationsQuery: "?siteId=toxodb",
    expectConversations: "ok",
    expectEnrichmentTabs: true,
  },
  {
    siteId: "tritrypdb",
    title: "leishmania virulence factors",
    rounds: [
      {
        prompt: "I'm investigating virulence factors in Leishmania major",
        reply: /have not built anything yet/i,
      },
      {
        prompt: "What surface proteases are involved in host macrophage invasion?",
        reply: /\[mock\].*surface/i,
      },
    ],
    sets: [{ name: "Leishmania Virulence Factors", genes: "all" }],
    conversationsQuery: "",
    expectConversations: "non-empty",
    expectEnrichmentTabs: true,
    followUp: {
      prompt:
        "The enrichment shows interesting protease pathways, what about drug targets?",
      reply: /\[mock\].*drug targets/i,
    },
  },
  {
    siteId: "cryptodb",
    title: "cryptosporidium intestinal infection",
    rounds: [
      {
        prompt: "I'm studying Cryptosporidium parvum intestinal infection mechanisms",
        reply: /\[mock\]/,
      },
      {
        prompt: "What oocyst wall proteins are important for environmental survival?",
        reply: /\[mock\].*oocyst/i,
      },
    ],
    sets: [
      { name: "Crypto Effectors", genes: "all" },
      { name: "COWP Subset", genes: "subset" },
    ],
    operation: { operation: "minus", count: (full, subset) => full - subset },
    conversationsQuery: "?siteId=cryptodb",
    expectConversations: "ok",
    expectEnrichmentTabs: false,
  },
  {
    siteId: "fungidb",
    title: "fungal pathogenesis",
    rounds: [
      {
        prompt: "I'm researching antifungal drug targets in Aspergillus fumigatus",
        reply: /\[mock\]/,
      },
      {
        prompt: "What cell wall biosynthesis enzymes are potential drug targets?",
        reply: /\[mock\].*cell wall/i,
      },
      {
        prompt: "Particularly interested in glucan synthase and chitin synthase",
        reply: /\[mock\].*glucan/i,
      },
    ],
    sets: [{ name: "Antifungal Targets", genes: "all" }],
    conversationsQuery: "",
    expectConversations: "ok",
    expectEnrichmentTabs: true,
    panels: ["Results Table", "Distribution Explorer"],
    expectPasteSource: true,
    followUp: {
      prompt:
        "The enrichment confirms cell wall synthesis pathways, what's the clinical relevance?",
      reply: /\[mock\].*clinical/i,
    },
  },
];

interface GeneSetRow {
  readonly id: string;
  readonly name: string;
  readonly geneCount: number;
  readonly geneIds: string[];
  readonly siteId: string;
  readonly source: string;
}

for (const journey of JOURNEYS) {
  test.describe(`${journey.title} journey on ${journey.siteId}`, () => {
    test("chat, strategy, gene sets, enrichment and API verification", async ({
      chatPage,
      graphPage,
      page,
      seedData,
      apiClient,
      sitePicker,
      workbenchSidebarPage,
      workbenchMainPage,
    }) => {
      const site = seedData.siteData[journey.siteId];
      if (site === undefined) {
        throw new Error(`${journey.siteId} seed data missing`);
      }
      const genes = site.geneIds;
      const fullCount = genes.length;
      const subsetGenes = genes.slice(0, 2);
      const subsetCount = subsetGenes.length;
      const setsPath = `/api/v1/gene-sets?siteId=${journey.siteId}`;

      const readSets = async (): Promise<GeneSetRow[]> => {
        const resp = await apiClient.get(setsPath);
        expect(resp.ok()).toBeTruthy();
        return (await resp.json()) as GeneSetRow[];
      };

      const clearSets = async (): Promise<void> => {
        const resp = await apiClient.get(setsPath);
        if (!resp.ok()) return;
        const stale = (await resp.json()) as GeneSetRow[];
        await Promise.all(
          stale.map((gs) => apiClient.delete(`/api/v1/gene-sets/${gs.id}`)),
        );
      };

      await clearSets();

      await chatPage.goto();
      await sitePicker.selectSite(journey.siteId);
      await sitePicker.expectCurrentSite(journey.siteId);

      for (const round of journey.rounds) {
        await chatPage.send(round.prompt);
        await chatPage.expectAssistantMessage(round.reply);
        await chatPage.expectIdle();
      }

      await chatPage.send(MOCK_PLAN_PROMPT);
      await graphPage.expectRailPanel();
      await chatPage.expectIdle();

      const conversations = await apiClient.get(
        `/api/v1/conversations${journey.conversationsQuery}`,
      );
      expect(conversations.ok()).toBeTruthy();
      if (journey.expectConversations === "non-empty") {
        const rows = (await conversations.json()) as unknown[];
        expect(rows.length).toBeGreaterThan(0);
      }

      // The build creates gene sets of its own, so the manual assertions
      // below start from zero.
      await clearSets();
      await workbenchSidebarPage.goto();

      for (const spec of journey.sets) {
        const ids = spec.genes === "all" ? genes : subsetGenes;
        await workbenchSidebarPage.openAddModal();
        await page.getByLabel(/name/i).fill(spec.name);
        await page.getByLabel(/gene ids/i).fill(ids.join("\n"));
        await page.getByRole("button", { name: /add gene set/i }).click();
        await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });
        await workbenchSidebarPage.expectSetGeneCount(spec.name, ids.length);
      }
      await workbenchSidebarPage.expectSetCount(journey.sets.length);

      const created = await readSets();
      expect(created.length).toBe(journey.sets.length);
      const primary = journey.sets[0];
      if (primary === undefined) throw new Error("a journey pastes at least one set");
      const primaryRow = created.find((gs) => gs.name === primary.name);
      expect(primaryRow).toBeDefined();
      expect(primaryRow?.geneCount).toBe(fullCount);
      expect(primaryRow?.geneIds).toHaveLength(fullCount);
      expect(primaryRow?.siteId).toBe(journey.siteId);
      if (journey.expectPasteSource === true) {
        expect(primaryRow?.source).toBe("paste");
      }

      await workbenchSidebarPage.activateSet(primary.name);
      await workbenchMainPage.expectActiveSetHeader(primary.name, fullCount);

      await workbenchMainPage.runEnrichmentAndVerifyResults();
      if (journey.expectEnrichmentTabs) {
        await workbenchMainPage.expectEnrichmentTypeTabs();
      }
      await workbenchMainPage.expectEnrichmentResultsWithData();

      for (const panel of journey.panels ?? []) {
        await workbenchMainPage.expectPanelVisible(panel);
      }

      const operation = journey.operation;
      if (operation !== undefined) {
        const second = journey.sets[1];
        if (second === undefined) {
          throw new Error("a set operation needs two sets");
        }
        const expected = operation.count(fullCount, subsetCount);

        await workbenchSidebarPage.selectSet(primary.name);
        await workbenchSidebarPage.selectSet(second.name);

        const opButton = page.getByRole("button", {
          name: new RegExp(operation.operation, "i"),
        });
        await expect(opButton).toBeVisible({ timeout: 10_000 });

        // The compose bar opens on Intersect, so a different operation must
        // be chosen before its count can be previewed.
        await opButton.click();
        await workbenchSidebarPage.expectComposeResultCount(expected);

        await workbenchSidebarPage.performOperation(operation.operation);
        await workbenchSidebarPage.expectSetCount(journey.sets.length + 1);

        const afterOperation = await readSets();
        expect(afterOperation.length).toBe(journey.sets.length + 1);
        const derived = afterOperation.find((gs) => gs.source === "derived");
        expect(derived).toBeDefined();
        expect(derived?.geneCount).toBe(expected);
      }

      const followUp = journey.followUp;
      if (followUp !== undefined) {
        await page.goto("/");
        await chatPage.send(followUp.prompt);
        await chatPage.expectAssistantMessage(followUp.reply);
        await chatPage.expectIdle();
      }
    });
  });
}
