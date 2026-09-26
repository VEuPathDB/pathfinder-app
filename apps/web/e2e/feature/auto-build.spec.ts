/**
 * What one build leaves behind: the WDK strategy, the stored step, the gene set
 * imported from it, and all of them again after a reload. Also the echo reply
 * a message with no arc token gets. Only the model is mocked.
 */

import type { GeneSet } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import type { ApiClient } from "../fixtures/api-client";
import { LAYOUTS, SIGNAL_PEPTIDE } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import {
  readAst,
  readConversation,
  siteGeneIdPrefix,
  siteOrganism,
} from "../fixtures/site-reads";
import { buildOn } from "../fixtures/strategy-builds";

/** The gene set the build of WDK strategy `wdkStrategyId` imported, once it is there. */
async function builtGeneSet(
  api: ApiClient,
  siteId: string,
  wdkStrategyId: number,
): Promise<GeneSet> {
  let found: GeneSet | undefined;
  await expect
    .poll(
      async () => {
        const resp = await api.get(`/api/v1/gene-sets?siteId=${siteId}`);
        expect(resp.status()).toBe(200);
        const sets = (await resp.json()) as GeneSet[];
        found = sets.find((set) => set.wdkStrategyId === wdkStrategyId);
        return found?.id ?? "";
      },
      { timeout: 60_000 },
    )
    .not.toBe("");
  if (found === undefined) throw new Error("the build imported no gene set");
  return found;
}

test.describe("Auto-build", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("a build stores its WDK strategy, its step and its gene set, and a reload keeps them", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt(
        "single",
        `Find ${siteOrganism(siteId)} genes whose proteins have a predicted signal peptide.`,
      ),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    const built = await readConversation(apiClient, id);
    const wdkStrategyId = built.wdkStrategyId ?? 0;
    expect(wdkStrategyId).toBeGreaterThan(0);
    const steps = built.steps ?? [];
    expect(steps.map((step) => step.searchName)).toEqual([SIGNAL_PEPTIDE]);
    expect(steps.map((step) => step.recordType)).toEqual([
      (await readAst(apiClient, id)).recordType,
    ]);
    const wdkStepIds = steps.map((step) => step.wdkStepId);
    expect(wdkStepIds.every((wdk) => (wdk ?? 0) > 0)).toBe(true);

    const geneSet = await builtGeneSet(apiClient, siteId, wdkStrategyId);
    expect(geneSet.source).toBe("strategy");
    expect(geneSet.siteId).toBe(siteId);
    expect(geneSet.geneCount).toBe(counts.root);
    expect(geneSet.geneIds).toHaveLength(geneSet.geneCount);
    const prefix = siteGeneIdPrefix(siteId);
    expect(geneSet.geneIds.filter((gene) => !gene.startsWith(prefix))).toEqual([]);
    expect((await readConversation(apiClient, id)).geneSetId).toBe(geneSet.id);

    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    const reloaded = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    expect(reloaded.root).toBe(counts.root);
    const after = await readConversation(apiClient, id);
    expect(after.wdkStrategyId).toBe(wdkStrategyId);
    expect((after.steps ?? []).map((step) => step.wdkStepId)).toEqual(wdkStepIds);
    const kept = await builtGeneSet(apiClient, siteId, wdkStrategyId);
    expect(kept.id).toBe(geneSet.id);
    expect(kept.geneCount).toBe(geneSet.geneCount);
  });
});

test.describe("Echo replies", () => {
  test.beforeEach(async ({ chatPage, siteId }) => {
    await chatPage.startOn(siteId);
  });

  test("a message with no arc token is echoed and builds nothing", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    await chatPage.sendTurn("hello world", /\[mock\].*hello world/);

    await expect(chatPage.assistantReply(/\[mock\].*hello world/)).toHaveCount(1);
    await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
    const id = chatPage.lastStrategyId ?? "";
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
  });

  test("each of two messages gets its own reply", async ({ chatPage }) => {
    await chatPage.sendTurn("first message", /\[mock\].*first message/);
    await chatPage.sendTurn("second message", /\[mock\].*second message/);

    await expect(chatPage.assistantMessages).toHaveCount(2);
    await expect(chatPage.assistantReply(/\[mock\].*first message/)).toHaveCount(1);
    await expect(chatPage.assistantReply(/\[mock\].*second message/)).toHaveCount(1);
  });
});
