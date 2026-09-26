import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";
import type { ChatPage } from "../pages/chat.page";
import type { SidebarPage } from "../pages/sidebar.page";
import type { ApiClient } from "../fixtures/api-client";
import { openConversationId } from "../pages/navigation";

/**
 * Feature: Recently deleted (soft-deleted) conversations.
 *
 * Sidebar Delete soft-deletes every conversation: it POSTs `/dismiss` and leaves
 * the linked WDK strategy alone. The Recently deleted section in the sidebar
 * shows these conversations with a Restore button to bring them back.
 *
 * Strategies are created via chat UI (immediately visible in sidebar), then a
 * unique wdkStrategyId is PATCHed on to simulate a WDK-linked strategy.
 */

/**
 * Helper: create a strategy via chat UI and PATCH a unique wdkStrategyId
 * onto it, making it behave as a WDK-linked strategy for delete semantics.
 */
async function makeWdkLinked(
  page: Page,
  chatPage: ChatPage,
  sidebarPage: SidebarPage,
  apiClient: ApiClient,
  message = "conversation for dismissed test",
): Promise<string> {
  await chatPage.send(message);
  await chatPage.expectAssistantMessage(/\[mock\]/);
  await sidebarPage.expectAtLeastOneConversation();

  const strategyId = await openConversationId(page);

  const uniqueWdkId = Math.floor(Date.now() / 1000) + Math.floor(Math.random() * 10000);
  const patchResp = await apiClient.patch(`/api/v1/conversations/${strategyId}`, {
    data: { wdkStrategyId: uniqueWdkId },
  });
  expect(patchResp.ok()).toBeTruthy();

  return strategyId;
}

/** Start a new chat and wait for the strategy creation to complete. */
async function startNewChat(page: Page, sidebarPage: SidebarPage) {
  // "New conversation" opens a fresh, lazily-created conversation (no /open POST until
  // the first message). Just wait for the empty composer to be ready.
  await sidebarPage.createNew();
  await expect(page.getByTestId("message-input")).toBeVisible({ timeout: 15_000 });
}

/** Wait for the soft-delete (dismiss) 204 targeting a specific strategy. */
function waitForDismiss(page: Page, strategyId: string) {
  return page.waitForResponse(
    (resp) =>
      resp.url().includes(`/conversations/${strategyId}/dismiss`) &&
      resp.request().method() === "POST" &&
      resp.status() === 204,
  );
}

/** Wait for a POST restore response targeting a specific strategy. */
function waitForRestore(page: Page, strategyId: string) {
  return page.waitForResponse(
    (resp) =>
      resp.url().includes(`/conversations/${strategyId}/restore`) &&
      resp.request().method() === "POST" &&
      resp.ok(),
  );
}

test.describe("Recently deleted conversations: complex flows", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage, apiClient }) => {
    // Purge prior conversations (incl. dismissed) so dismissed-count
    // assertions aren't polluted by earlier tests in this serial suite.
    await apiClient.delete("/api/v1/user/data?deleteWdk=true");
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("delete -> restore -> delete -> restore round-trip", async ({
    chatPage,
    sidebarPage,
    apiClient,
    page,
  }) => {
    const strategyId = await makeWdkLinked(page, chatPage, sidebarPage, apiClient);

    // First dismiss (UI state is the source of truth; a response-wait
    // race on the second cycle made this flaky.)
    await sidebarPage.delete(strategyId);
    await expect(sidebarPage.item(strategyId)).not.toBeVisible({
      timeout: 15_000,
    });
    await sidebarPage.expectDismissedCount(1);

    // First restore
    await sidebarPage.expandDismissed();
    await sidebarPage.restoreDismissed(strategyId);
    await expect(sidebarPage.item(strategyId)).toBeVisible({
      timeout: 15_000,
    });
    await sidebarPage.expectNoDismissedSection();

    // Second dismiss
    await sidebarPage.delete(strategyId);
    await expect(sidebarPage.item(strategyId)).not.toBeVisible({
      timeout: 15_000,
    });
    await sidebarPage.expectDismissedCount(1);

    // Second restore
    await sidebarPage.expandDismissed();
    await sidebarPage.restoreDismissed(strategyId);
    await expect(sidebarPage.item(strategyId)).toBeVisible({
      timeout: 15_000,
    });
    await sidebarPage.expectNoDismissedSection();

    // API confirms fully active.
    const resp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(resp.ok()).toBeTruthy();
  });

  test("multiple dismissed strategies - restore one at a time", async ({
    chatPage,
    sidebarPage,
    apiClient,
    page,
  }) => {
    // Create first WDK strategy.
    const id1 = await makeWdkLinked(
      page,
      chatPage,
      sidebarPage,
      apiClient,
      "find kinase genes",
    );

    // Create second WDK strategy (new chat first so sidebar has 2 items).
    await startNewChat(page, sidebarPage);
    const id2 = await makeWdkLinked(
      page,
      chatPage,
      sidebarPage,
      apiClient,
      "find transporter genes",
    );

    // Dismiss both. (UI state is the source of truth; response-waits raced.)
    await sidebarPage.delete(id2);
    await expect(sidebarPage.item(id2)).not.toBeVisible({ timeout: 15_000 });
    await sidebarPage.expectDismissedCount(1);

    // Wait for id1 to be visible after sidebar refetch before deleting it.
    await expect(sidebarPage.item(id1)).toBeVisible({ timeout: 10_000 });

    await sidebarPage.delete(id1);
    await expect(sidebarPage.item(id1)).not.toBeVisible({ timeout: 15_000 });
    await sidebarPage.expectDismissedCount(2);

    // Expand dismissed - both visible.
    await sidebarPage.expandDismissed();
    await sidebarPage.expectDismissedItemVisible(id1);
    await sidebarPage.expectDismissedItemVisible(id2);

    // Restore one - count drops to 1.
    await sidebarPage.restoreDismissed(id1);
    await expect(sidebarPage.item(id1)).toBeVisible({ timeout: 15_000 });
    await sidebarPage.expectDismissedCount(1);

    // Restore the other - dismissed section disappears.
    await sidebarPage.restoreDismissed(id2);
    await expect(sidebarPage.item(id2)).toBeVisible({ timeout: 15_000 });
    await sidebarPage.expectNoDismissedSection();
  });

  test("restored strategy is fully functional - can receive messages", async ({
    chatPage,
    sidebarPage,
    apiClient,
    page,
  }) => {
    const strategyId = await makeWdkLinked(
      page,
      chatPage,
      sidebarPage,
      apiClient,
      "find membrane protein genes",
    );

    // Dismiss it.
    const dismissCompleted = waitForDismiss(page, strategyId);
    await sidebarPage.delete(strategyId);
    await dismissCompleted;

    await expect(sidebarPage.item(strategyId)).not.toBeVisible({
      timeout: 10_000,
    });
    await sidebarPage.expectDismissedCount(1);

    // Restore it.
    await sidebarPage.expandDismissed();
    const restoreCompleted = waitForRestore(page, strategyId);
    await sidebarPage.restoreDismissed(strategyId);
    await restoreCompleted;

    await expect(sidebarPage.item(strategyId)).toBeVisible({
      timeout: 15_000,
    });

    // Select the restored strategy.
    await sidebarPage.selectConversation(strategyId);

    // Send a new message to verify the conversation is fully functional.
    await chatPage.send("find ribosomal genes");
    await chatPage.expectAssistantMessage(/ribosomal genes/);

    // API confirms strategy still exists and is accessible.
    const resp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(resp.ok()).toBeTruthy();
  });
});
