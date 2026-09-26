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
});
