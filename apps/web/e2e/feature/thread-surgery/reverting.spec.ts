/**
 * Reverting a thread to an earlier user message: the transcript truncates in
 * place, the strategy goes back to the state that message was answered
 * against, the thread carries on, and a revert to an already-deleted message
 * is a no-op the dialog does not error on.
 */

import { test, expect } from "../../fixtures/test";
import { CSRF_HEADERS, fetchUserMessageIds } from "../../fixtures/api-client";
import {
  BUILD_ONE,
  BUILT_ORGANISM,
  EDITED_ORGANISM,
  EDIT_ORGANISM,
  SITE_ID,
  SUBSTITUTED,
  VERIFIED,
  echoOf,
} from "./prompts";
import { taxonOrganism } from "./strategyState";

const ASK_COUNT = "how many genes are in this strategy?";
const ASK_AGAIN = "and how many now?";

test.describe("Thread reverting", () => {
  // Each journey drives three to five turns through the worker, and one queued
  // behind another suite's build waits minutes.
  test.describe.configure({ timeout: 600_000 });

  test.beforeEach(async ({ chatPage, sitePicker }) => {
    await chatPage.goto();
    await sitePicker.selectSite(SITE_ID);
    await chatPage.newChat(SITE_ID);
  });

  test("a revert truncates the transcript in place and restores that turn's strategy", async ({
    chatPage,
    graphPage,
    apiClient,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);

    const conversationId = chatPage.lastStrategyId as string;
    expect(await taxonOrganism(apiClient, conversationId)).toEqual([BUILT_ORGANISM]);

    await chatPage.sendTurn(EDIT_ORGANISM, SUBSTITUTED);
    expect(await taxonOrganism(apiClient, conversationId)).toEqual([EDITED_ORGANISM]);

    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));

    const replacement = "leave the strategy as it was";
    await chatPage.openEditDialog(EDIT_ORGANISM, replacement);
    const revert = await chatPage.confirmRevert();
    expect(revert.status()).toBe(204);

    // The transcript truncates without a reload.
    await expect(chatPage.userMessage(replacement)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessage(EDIT_ORGANISM)).toHaveCount(0);
    await expect(chatPage.userMessage(ASK_COUNT)).toHaveCount(0);
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1);
    await expect(chatPage.editDialogError).toHaveCount(0);
    await chatPage.awaitTurn(echoOf(replacement));

    // The strategy is the one the reverted-to message was answered against.
    await expect
      .poll(() => taxonOrganism(apiClient, conversationId), { timeout: 30_000 })
      .toEqual([BUILT_ORGANISM]);
    await graphPage.openRailStrategyPanel();
    expect(await graphPage.railStepCount()).toBe(1);
    await expect(graphPage.railFooter).toContainText("1 step");
  });

  test("a reverted thread carries on, and the deleted turns stay gone after a reload", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);
    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));
    await chatPage.sendTurn(ASK_AGAIN, echoOf(ASK_AGAIN));

    const conversationId = chatPage.lastStrategyId as string;
    const replacement = "let us keep this simple";
    await chatPage.openEditDialog(ASK_COUNT, replacement);
    expect((await chatPage.confirmRevert()).status()).toBe(204);

    await expect(chatPage.userMessage(replacement)).toHaveCount(1, { timeout: 30_000 });
    await chatPage.awaitTurn(echoOf(replacement));

    // The next turn lands on the same thread, not on a new one.
    const followUp = "one last question here";
    await chatPage.sendTurn(followUp, echoOf(followUp));
    await expect(page).toHaveURL(new RegExp(`/conversation/${conversationId}$`));

    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 30_000 });
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessage(replacement)).toHaveCount(1);
    await expect(chatPage.userMessage(followUp)).toHaveCount(1);
    await expect(chatPage.userMessage(ASK_COUNT)).toHaveCount(0);
    await expect(chatPage.userMessage(ASK_AGAIN)).toHaveCount(0);
    expect(await fetchUserMessageIds(apiClient, conversationId)).toHaveLength(3);
  });

  test("a revert to an already-deleted message is a no-op the dialog does not error on", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);
    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));
    await chatPage.sendTurn(ASK_AGAIN, echoOf(ASK_AGAIN));

    const conversationId = chatPage.lastStrategyId as string;
    const messageIds = await fetchUserMessageIds(apiClient, conversationId);
    expect(messageIds).toHaveLength(3);
    const target = messageIds[1] as string;

    // Cut the thread out from under the open page.
    const first = await apiClient.post(
      `/api/v1/conversations/${conversationId}/revert-to-message`,
      { headers: CSRF_HEADERS, data: { messageId: target } },
    );
    expect(first.status()).toBe(204);
    expect(await fetchUserMessageIds(apiClient, conversationId)).toEqual([
      messageIds[0],
    ]);

    // The stale page still offers the message, and reverting to it again is
    // answered rather than refused.
    const replacement = "second thoughts about this";
    await chatPage.openEditDialog(ASK_COUNT, replacement);
    const second = await chatPage.confirmRevert();
    expect(second.status()).toBe(204);

    await expect(chatPage.editDialogError).toHaveCount(0);
    await expect(page.getByTestId("edit-revert-button")).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(chatPage.userMessage(replacement)).toHaveCount(1, { timeout: 30_000 });
    await chatPage.awaitTurn(echoOf(replacement));

    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 30_000 });
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessage(replacement)).toHaveCount(1);
    await expect(chatPage.userMessage(ASK_COUNT)).toHaveCount(0);
    await expect(chatPage.userMessage(ASK_AGAIN)).toHaveCount(0);
    expect(await fetchUserMessageIds(apiClient, conversationId)).toHaveLength(2);
  });
});
