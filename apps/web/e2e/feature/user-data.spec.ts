import type { ConversationResponse, GeneSet } from "@pathfinder/shared";
import type { PurgeUserDataResponse } from "@pathfinder/shared/generated/types/PurgeUserDataResponse";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import {
  type ApiClient,
  type ConversationRow,
  listBody,
  listConversations,
} from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { siteOrganism } from "../fixtures/site-reads";

/**
 * Feature: `DELETE /api/v1/user/data` without a site clears the user's data on
 * every site, against the real database and the real WDK strategies. The Data
 * tab's own flows are A4 and A7 in `uat/settings-account.spec.ts`.
 */

/** Every conversation of the calling user, on every site. */
async function allConversations(apiClient: ApiClient): Promise<ConversationRow[]> {
  return listBody(await apiClient.get("/api/v1/conversations"), "conversations");
}

/** The calling user's gene sets, on every site. */
async function allGeneSets(apiClient: ApiClient): Promise<GeneSet[]> {
  return listBody(await apiClient.get("/api/v1/gene-sets"), "gene sets");
}

test.describe("User data purge across sites", { tag: "@named-site" }, () => {
  test("purge ALL data deletes across all sites", async ({
    chatPage,
    apiClient,
    sitePicker,
  }) => {
    await chatPage.goto();

    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");
    await chatPage.send("plasmodb data");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    await sitePicker.selectSite("toxodb");
    await chatPage.newChat("toxodb");
    await chatPage.send("toxodb data");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    expect((await listConversations(apiClient, "plasmodb")).length).toBeGreaterThan(0);
    expect((await listConversations(apiClient, "toxodb")).length).toBeGreaterThan(0);

    const purgeResp = await apiClient.delete("/api/v1/user/data");
    expect(purgeResp.ok()).toBe(true);
    const result = (await purgeResp.json()) as PurgeUserDataResponse;
    expect(result.ok).toBe(true);
    expect(result.deleted.strategies).toBeGreaterThanOrEqual(2);

    expect(await listConversations(apiClient, "plasmodb")).toHaveLength(0);
    expect(await listConversations(apiClient, "toxodb")).toHaveLength(0);
  });
});

test.describe("User data purge after a build", { tag: "@turn" }, () => {
  test("purge deletes built strategies with a wdkStrategyId and gene sets", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    test.setTimeout(600_000);
    await chatPage.startOn(siteId);
    await chatPage.sendAndSettle(
      prompt(
        "single",
        `Find ${siteOrganism(siteId)} genes whose proteins have a predicted signal peptide.`,
      ),
    );
    const strategyId = chatPage.lastStrategyId ?? "";
    await expectBuild(page, apiClient, strategyId, siteId, LAYOUTS.single);
    await chatPage.sendAndSettle(
      prompt(
        "save-gene-set",
        "Save the genes of this strategy as a gene set named purge check.",
      ),
    );
    await expect(
      page.getByTestId("data-gene-set").filter({ hasText: "purge check" }),
    ).toBeVisible({ timeout: 60_000 });

    const stratResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    const strategy = (await stratResp.json()) as ConversationResponse;
    expect(strategy.wdkStrategyId ?? 0).toBeGreaterThan(0);
    expect((await allGeneSets(apiClient)).length).toBeGreaterThan(0);

    const purgeResp = await apiClient.delete("/api/v1/user/data?deleteWdk=true");
    expect(purgeResp.ok()).toBe(true);
    const result = (await purgeResp.json()) as PurgeUserDataResponse;
    expect(result.ok).toBe(true);
    expect(result.deleted.strategies).toBeGreaterThan(0);
    expect(result.deleted.geneSets).toBeGreaterThan(0);

    const afterStrat = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(afterStrat.status()).toBe(404);
    expect(await allGeneSets(apiClient)).toHaveLength(0);
    expect(await allConversations(apiClient)).toHaveLength(0);
  });
});
