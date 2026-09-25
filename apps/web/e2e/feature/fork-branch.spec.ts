import { test, expect } from "../fixtures/test";

/**
 * Feature: branching a conversation from a message.
 *
 * Branching is a per-message action ("Branch to a new conversation from here" on an
 * assistant reply) that forks the conversation into a brand-new chat, copying
 * the prior context. Verified end-to-end against the real fork endpoint.
 */
test.describe("Fork Branch", () => {
  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("user forks from a message and lands in a new branched conversation", async ({
    chatPage,
    page,
  }) => {
    await chatPage.sendTurn("show me kinase genes", /\[mock\]/);

    const originalId = chatPage.lastStrategyId;
    expect(originalId).toBeTruthy();

    const branchId = await chatPage.branchFromAssistantReply(/\[mock\]/);

    // Navigated to a new conversation, distinct from the original.
    expect(branchId).not.toBe(originalId);
    await expect(page).toHaveURL(/\/conversation\/[0-9a-f-]+/);

    // The branched conversation keeps the prior user message.
    await expect(
      page.locator(".is-user").filter({ hasText: "show me kinase genes" }),
    ).toBeVisible({ timeout: 15_000 });
  });
});
