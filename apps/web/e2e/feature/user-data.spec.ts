import { test, expect } from "../fixtures/test";
import { MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";
import {
  type ApiClient,
  type ConversationRow,
  E2E_SITE_IDS,
  listBody,
  listConversations,
} from "../fixtures/api-client";

interface SeedFrame {
  type: string;
  message: string;
}

interface SeedItemErrorFrame extends SeedFrame {
  type: "seed_item_error";
  name: string;
  error: string;
}

interface SeedCompleteFrame extends SeedFrame {
  type: "seed_complete";
  total: number;
  strategiesCreated: number;
  controlSetsCreated: number;
  failed: number;
  error: string | null;
}

/** The typed frames of one `/api/v1/seed` stream. */
function seedFrames(body: string): SeedFrame[] {
  return body
    .split("\n")
    .filter((line) => line.startsWith("data: ") && line.trim() !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)) as SeedFrame);
}

/** Every conversation of the calling user, on every site. */
async function allConversations(apiClient: ApiClient): Promise<ConversationRow[]> {
  return listBody(await apiClient.get("/api/v1/conversations"), "conversations");
}

/** The calling user's gene sets, on one site or on every site. */
async function geneSets(apiClient: ApiClient, siteId?: string): Promise<unknown[]> {
  const query = siteId === undefined ? "" : `?siteId=${siteId}`;
  return listBody(await apiClient.get(`/api/v1/gene-sets${query}`), "gene sets");
}

/**
 * Feature: User data purge, verified against real PostgreSQL.
 *
 * Tests that DELETE /api/v1/user/data clears ALL data:
 * - strategies (active + dismissed) across all sites
 * - gene sets across all sites
 * - WDK strategies (best-effort)
 */
test.describe("User Data Purge", () => {
  test("purge site data deletes strategies and gene sets for that site only", async ({
    chatPage,
    apiClient,
    sitePicker,
    page,
  }) => {
    // Create data on plasmodb: a conversation and a gene set saved from it.
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");
    await chatPage.send("test message for plasmodb");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();
    await chatPage.send("Save PF3D7_0709000 and PF3D7_1133400 as a gene set");
    await expect(page.getByTestId("data-gene-set")).toBeVisible({ timeout: 90_000 });
    await chatPage.expectIdle();

    // Verify data exists
    expect((await listConversations(apiClient, "plasmodb")).length).toBeGreaterThan(0);
    expect((await geneSets(apiClient, "plasmodb")).length).toBeGreaterThan(0);

    // Purge plasmodb data
    const purgeResp = await apiClient.delete("/api/v1/user/data?siteId=plasmodb");
    expect(purgeResp.ok()).toBeTruthy();
    const result = await purgeResp.json();
    expect(result.ok).toBe(true);
    expect(result.deleted.strategies).toBeGreaterThan(0);
    expect(result.deleted.geneSets).toBeGreaterThan(0);

    // Verify data is gone
    expect(await listConversations(apiClient, "plasmodb")).toHaveLength(0);
    expect(await geneSets(apiClient, "plasmodb")).toHaveLength(0);
  });

  test("purge ALL data deletes across all sites", async ({
    chatPage,
    apiClient,
    sitePicker,
  }) => {
    // Create data on two different sites
    await chatPage.goto();

    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");
    await chatPage.send("plasmodb data");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    await sitePicker.selectSite("toxodb");
    await chatPage.newChat("toxodb");
    await chatPage.send("toxodb data");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    // Verify data on both sites
    expect((await listConversations(apiClient, "plasmodb")).length).toBeGreaterThan(0);
    expect((await listConversations(apiClient, "toxodb")).length).toBeGreaterThan(0);

    // Purge ALL (no siteId)
    const purgeResp = await apiClient.delete("/api/v1/user/data");
    expect(purgeResp.ok()).toBeTruthy();
    const result = await purgeResp.json();
    expect(result.ok).toBe(true);
    expect(result.deleted.strategies).toBeGreaterThanOrEqual(2);

    // Both sites empty (active list)
    expect(await listConversations(apiClient, "plasmodb")).toHaveLength(0);
    expect(await listConversations(apiClient, "toxodb")).toHaveLength(0);
  });

  test("seed all databases then purge deletes everything on every site", async ({
    apiClient,
  }) => {
    test.setTimeout(300_000);
    // The walk covers the sites the e2e config serves, and the api lists no other.
    const sites = await listBody<{ id: string }>(
      await apiClient.get("/api/v1/sites"),
      "sites",
    );
    expect(sites.map((s) => s.id).sort()).toEqual([...E2E_SITE_IDS].sort());

    // Seed all databases - creates strategies + control sets across all sites.
    const seedResp = await apiClient.post("/api/v1/seed", {
      headers: { Accept: "text/event-stream" },
      timeout: 300_000,
    });
    expect(seedResp.ok()).toBeTruthy();
    // A seed that creates nothing still ends with `seed_complete`, so the
    // counters decide, and the item errors name what VEuPathDB refused.
    const frames = seedFrames(await seedResp.text());
    const itemErrors = frames
      .filter((f): f is SeedItemErrorFrame => f.type === "seed_item_error")
      .map((f) => `${f.name}: ${f.error}`);
    const complete = frames.find(
      (f): f is SeedCompleteFrame => f.type === "seed_complete",
    );
    if (complete === undefined) {
      throw new Error(
        `seed stream carried no seed_complete frame; item errors: ${itemErrors.join(" | ")}`,
      );
    }
    expect(complete.error, `seed reported a top-level failure`).toBe(null);
    expect(
      complete.strategiesCreated,
      `seed created 0 of ${String(complete.total)} strategies (${String(complete.failed)} failed): ${itemErrors.slice(0, 5).join(" | ")}`,
    ).toBeGreaterThan(0);

    // Verify: strategies exist. Their WDK ids are the purge's target set:
    // the shared account also holds strategies this run did not create, and
    // the purge must not touch those.
    const beforeList = await allConversations(apiClient);
    expect(beforeList.length).toBeGreaterThan(0);
    const strategiesBefore = beforeList.length;
    const ourWdkStrategies: { siteId: string; wdkStrategyId: number }[] = [];
    for (const conv of beforeList) {
      if (conv.wdkStrategyId != null) {
        ourWdkStrategies.push({
          siteId: conv.siteId,
          wdkStrategyId: conv.wdkStrategyId,
        });
      }
    }
    expect(ourWdkStrategies.length).toBeGreaterThan(0);

    // Verify: gene sets exist
    const geneSetsBefore = (await geneSets(apiClient)).length;

    // Verify: strategies exist on multiple sites (not just one)
    let sitesWithStrategies = 0;
    for (const siteId of E2E_SITE_IDS) {
      if ((await listConversations(apiClient, siteId)).length > 0) {
        sitesWithStrategies++;
      }
    }
    expect(sitesWithStrategies).toBeGreaterThan(1);

    // Purge ALL data with deleteWdk=true. Deleting every seeded WDK strategy
    // across all sites is slow, so allow well beyond the default request timeout.
    const purgeResp = await apiClient.delete("/api/v1/user/data?deleteWdk=true", {
      timeout: 240_000,
    });
    expect(purgeResp.ok()).toBeTruthy();
    const result = (await purgeResp.json()) as {
      ok: boolean;
      deleted: {
        strategies: number;
        wdkStrategies: number;
        geneSets: number;
      };
    };
    expect(result.ok).toBe(true);
    // Background auto-import may create additional projections between list
    // and purge, so the count can be higher than strategiesBefore.
    expect(result.deleted.strategies).toBeGreaterThanOrEqual(strategiesBefore);
    expect(result.deleted.geneSets).toBeGreaterThanOrEqual(geneSetsBefore);
    expect(result.deleted.wdkStrategies).toBeGreaterThan(0);

    // Verify: ALL local strategies gone
    expect(await allConversations(apiClient)).toHaveLength(0);

    // Verify: ALL gene sets gone
    expect(await geneSets(apiClient)).toHaveLength(0);

    // Verify: dismissed list empty
    const afterDismissed = await listBody(
      await apiClient.get("/api/v1/conversations/dismissed"),
      "dismissed conversations",
    );
    expect(afterDismissed).toHaveLength(0);

    // CRITICAL: every strategy this run created is gone from WDK itself, so
    // re-opening it by its WDK id is refused rather than re-imported.
    for (const { siteId, wdkStrategyId } of ourWdkStrategies) {
      const reopen = await apiClient.post("/api/v1/conversations/open", {
        data: { siteId, wdkStrategyId },
      });
      expect(
        reopen.ok(),
        `purged strategy ${String(wdkStrategyId)} survived on WDK for ${siteId} - WDK deletion failed for this site`,
      ).toBe(false);
    }

    // Verify per-site: none of the purged strategies is listed anywhere.
    const purgedWdkIds = new Set(ourWdkStrategies.map((e) => e.wdkStrategyId));
    for (const siteId of E2E_SITE_IDS) {
      const listed = await listConversations(apiClient, siteId);
      const survivors = listed.filter(
        (conv) => conv.wdkStrategyId != null && purgedWdkIds.has(conv.wdkStrategyId),
      );
      expect(
        survivors.length,
        `purged strategies still listed on ${siteId} after purge`,
      ).toBe(0);
    }
  });

  test("purge deletes auto-built strategies with wdkStrategyId and gene sets", async ({
    chatPage,
    apiClient,
  }) => {
    // Seed: create a strategy with auto-build (real WDK strategy + gene set)
    await chatPage.goto();
    await chatPage.newChat();
    // A build prompt ends on the verification digest, not the plain echo.
    await chatPage.send(MOCK_PLAN_PROMPT);
    await chatPage.expectVerificationSuccess();
    await chatPage.expectIdle();

    // Verify auto-build created real data
    const strategyId = chatPage.lastStrategyId;
    const stratResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    const strategy = await stratResp.json();
    expect(strategy.wdkStrategyId).toBeTruthy();

    expect((await geneSets(apiClient)).length).toBeGreaterThan(0);

    // Purge ALL data with deleteWdk=true to fully remove everything.
    const purgeResp = await apiClient.delete("/api/v1/user/data?deleteWdk=true");
    expect(purgeResp.ok()).toBeTruthy();
    const result = await purgeResp.json();
    expect(result.ok).toBe(true);
    expect(result.deleted.strategies).toBeGreaterThan(0);
    expect(result.deleted.geneSets).toBeGreaterThan(0);

    // Verify: strategy hard-deleted (404)
    const afterStrat = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(afterStrat.status()).toBe(404);

    // Verify: gene sets gone
    expect(await geneSets(apiClient)).toHaveLength(0);

    // Verify: strategy list empty
    expect(await allConversations(apiClient)).toHaveLength(0);
  });
});
