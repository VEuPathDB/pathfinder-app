import { test, expect } from "../fixtures/test";
import { currentSiteId, openConversationId } from "../pages/navigation";

/**
 * Feature: the second assistant is reachable from the product.
 *
 * The sidebar names the assistants, the draft route carries the one the reader
 * picked, and the thread the first message creates is answered by that
 * assistant and keeps it.
 */
test.describe("Site help assistant", () => {
  test.describe.configure({ mode: "serial" });

  test("a thread opened against site help is answered by site help", async ({
    page,
    chatPage,
    apiClient,
  }) => {
    await chatPage.goto();
    const siteId = currentSiteId(page);

    await page.getByTestId("conversations-new-assistant-button").click();
    await page.getByTestId("new-chat-assistant-site_help").click();
    await page.waitForURL(
      (url) =>
        url.pathname === `/${siteId}/conversation` &&
        url.searchParams.get("assistant") === "site_help",
      { timeout: 60_000 },
    );

    // The thread says which assistant is about to answer it.
    await expect(page.getByTestId("chat-assistant-label")).toHaveText("Site help");

    await chatPage.send("which sites can I use?");
    await chatPage.expectAssistantMessage(/point you around/);
    await chatPage.expectIdle();

    // The conversation the first message created belongs to that assistant.
    const conversationId = await openConversationId(page);
    const response = await apiClient.get(`/api/v1/conversations/${conversationId}`);
    expect(response.ok()).toBeTruthy();
    const conversation = (await response.json()) as { assistantId?: string };
    expect(conversation.assistantId).toBe("site_help");

    // And the sidebar row names it, so a reader who comes back can tell.
    await chatPage.refreshConversationsButton.click();
    const row = page.locator(
      `[data-testid="conversation-item"][data-conversation-id="${conversationId}"]`,
    );
    await expect(row).toContainText("Site help", { timeout: 30_000 });
  });

  test("the plain new-chat button still opens a strategy thread", async ({
    page,
    chatPage,
    apiClient,
  }) => {
    await chatPage.goto();
    await chatPage.newChatButton.click();

    await chatPage.send("hello strategy builder");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    const conversationId = await openConversationId(page);
    const response = await apiClient.get(`/api/v1/conversations/${conversationId}`);
    expect(response.ok()).toBeTruthy();
    const conversation = (await response.json()) as { assistantId?: string };
    expect(conversation.assistantId).toBe("pathfinder");
  });
});
