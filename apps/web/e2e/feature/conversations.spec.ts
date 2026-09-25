import { test, expect } from "../fixtures/test";
import { fetchConversationMessages, listConversations } from "../fixtures/api-client";
import { currentSiteId } from "../pages/navigation";

/**
 * Feature: Conversations - CRUD verified against real PostgreSQL.
 */
test.describe("Conversations", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("new conversation persisted in PostgreSQL", async ({
    chatPage,
    sidebarPage,
    apiClient,
  }) => {
    await chatPage.send("create a new conversation");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await sidebarPage.expectAtLeastOneConversation();

    // API confirms strategy exists with messages - use captured ID for isolation
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();

    // Messages are reconstructed from the persisted event snapshot.
    const messages = await fetchConversationMessages(apiClient, strategyId);
    expect(messages.length).toBeGreaterThan(0);
  });

  test("create new conversation via button persists to DB", async ({
    chatPage,
    page,
    apiClient,
  }) => {
    await chatPage.send("first conversation");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    const siteId = currentSiteId(page);
    const midCount = (await listConversations(apiClient, siteId)).length;

    await chatPage.newChat();
    await expect(chatPage.composer).toBeVisible();

    expect(await listConversations(apiClient, siteId)).toHaveLength(midCount + 1);
  });

  test("rename conversation persists to PostgreSQL", async ({
    chatPage,
    sidebarPage,
    apiClient,
  }) => {
    await chatPage.send("conversation to rename");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    const conversationId = await sidebarPage.firstConversationId();
    await sidebarPage.rename(conversationId, "Renamed Strategy");
    await sidebarPage.expectConversationName(conversationId, /renamed strategy/i);

    // API confirms rename persisted
    const resp = await apiClient.get(`/api/v1/conversations/${conversationId}`);
    expect(resp.ok()).toBeTruthy();
    const strategy = await resp.json();
    expect(strategy.name).toMatch(/renamed strategy/i);
  });

  test("delete conversation removes from PostgreSQL", async ({
    chatPage,
    sidebarPage,
    page,
    apiClient,
  }) => {
    await chatPage.send("conversation to delete");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await sidebarPage.expectAtLeastOneConversation();

    const conversationId = await sidebarPage.firstConversationId();

    // Link a WDK strategy id so the dismissed row also carries the WDK link
    // the sidebar shows for a built strategy.
    const patchResp = await apiClient.patch(`/api/v1/conversations/${conversationId}`, {
      data: { wdkStrategyId: Math.floor(Date.now() / 1000) },
    });
    expect(patchResp.ok()).toBeTruthy();

    // Verify exists before delete
    const beforeResp = await apiClient.get(`/api/v1/conversations/${conversationId}`);
    expect(beforeResp.ok()).toBeTruthy();

    // Sidebar Delete soft-deletes: it POSTs /dismiss and leaves the WDK
    // strategy alone. Hard delete is the opt-in "delete linked strategy" path.
    const dismissCompleted = page.waitForResponse(
      (resp) =>
        resp.url().includes(`/conversations/${conversationId}/dismiss`) &&
        resp.request().method() === "POST",
    );
    await sidebarPage.delete(conversationId);
    await dismissCompleted;

    await expect(sidebarPage.item(conversationId)).not.toBeVisible({
      timeout: 10_000,
    });

    // API confirms soft-deleted (moved to dismissed).
    const dismissed = await listConversations(
      apiClient,
      currentSiteId(page),
      "dismissed",
    );
    expect(dismissed.map((d) => d.id)).toContain(conversationId);
  });

  test("search conversations filters list", async ({ chatPage, sidebarPage }) => {
    await chatPage.send("alpha query");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    await sidebarPage.createNew();
    await chatPage.send("beta query");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    await sidebarPage.search("alpha");
    await expect(sidebarPage.searchInput).toHaveValue("alpha");

    await sidebarPage.clearSearch();
    await expect(sidebarPage.searchInput).toHaveValue("");
  });
});
