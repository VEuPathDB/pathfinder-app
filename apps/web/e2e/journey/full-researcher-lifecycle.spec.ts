/**
 * The researcher's lifecycle on the project's site: two chat rounds, a build and
 * its gene set, a switch to another site that holds none of it, the settings,
 * and a last round after which the gene set is unchanged. Only the model is
 * mocked.
 */

import type { GeneSet } from "@pathfinder/shared";

import { test, expect } from "../fixtures/a11y";
import { prompt } from "../fixtures/arcs";
import type { ApiClient } from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readConversation, siteOrganism } from "../fixtures/site-reads";

async function geneSetsOn(api: ApiClient, siteId: string): Promise<GeneSet[]> {
  const resp = await api.get(`/api/v1/gene-sets?siteId=${siteId}`);
  expect(resp.status()).toBe(200);
  return (await resp.json()) as GeneSet[];
}

test.describe("Full researcher lifecycle", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("chat, build, gene set, another site, settings and a last round", async ({
    chatPage,
    sidebarPage,
    sitePicker,
    settingsPage,
    page,
    apiClient,
    siteId,
  }) => {
    const organism = siteOrganism(siteId);
    const otherSite = siteId === "toxodb" ? "plasmodb" : "toxodb";

    await chatPage.goto();
    await sitePicker.selectSite(siteId);
    await chatPage.newChat(siteId);

    await chatPage.sendTurn(
      `find drug resistance genes in ${organism}`,
      /\[mock\].*drug resistance/,
    );
    await chatPage.sendTurn(
      "I want to focus on chloroquine and artemisinin resistance mechanisms",
      /\[mock\].*chloroquine/,
    );

    await chatPage.sendAndSettle(
      prompt(
        "single",
        `Find ${organism} genes whose proteins have a predicted signal peptide.`,
      ),
    );
    const id = chatPage.lastStrategyId ?? "";
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    let geneSetId = "";
    await expect
      .poll(
        async () => {
          geneSetId = (await readConversation(apiClient, id)).geneSetId ?? "";
          return geneSetId;
        },
        { timeout: 60_000 },
      )
      .not.toBe("");
    const builtSet = (await geneSetsOn(apiClient, siteId)).find(
      (set) => set.id === geneSetId,
    );
    expect(builtSet?.geneCount ?? 0).toBeGreaterThan(0);

    await sitePicker.selectSite(otherSite);
    await sitePicker.expectCurrentSite(otherSite);
    expect(await geneSetsOn(apiClient, otherSite)).toEqual([]);

    await sitePicker.selectSite(siteId);
    await sitePicker.expectCurrentSite(siteId);
    await settingsPage.open();
    await settingsPage.expectAllTabsVisible();
    await settingsPage.openTab("Data");
    await settingsPage.close();

    await page.goto(`/${siteId}/conversation/${id}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await sidebarPage.expectAtLeastOneConversation();
    await chatPage.sendTurn(
      "Summarize my findings from the resistance gene analysis",
      /\[mock\].*findings/,
    );

    const finalSet = (await geneSetsOn(apiClient, siteId)).find(
      (set) => set.id === geneSetId,
    );
    expect(finalSet?.geneCount).toBe(builtSet?.geneCount);
  });
});
