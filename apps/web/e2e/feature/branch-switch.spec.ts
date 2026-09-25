import { test, expect } from "../fixtures/test";
import { currentSiteId } from "../pages/navigation";

/**
 * Feature: branching + switching between conversations.
 *
 * Branching forks the conversation into a new chat from a chosen message.
 * Switching back to the original conversation must preserve its messages.
 */
test.describe("Branch Switch", () => {
  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("switching back to original branch preserves prior messages", async ({
    chatPage,
    page,
  }) => {
    await chatPage.sendTurn("show me kinase genes", /\[mock\]/);

    const originalId = chatPage.lastStrategyId;
    expect(originalId).toBeTruthy();

    const branchId = await chatPage.branchFromAssistantReply(/\[mock\]/);
    expect(branchId).not.toBe(originalId);

    // Switch back to the original conversation - its messages are intact.
    await page.goto(`/${currentSiteId(page)}/conversation/${originalId}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator(".is-user").filter({ hasText: "show me kinase genes" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator(".is-assistant").filter({ hasText: /\[mock\]/ }),
    ).toBeVisible({ timeout: 15_000 });
  });
});
