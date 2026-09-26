/**
 * A revert to a message another revert already deleted is answered, not
 * refused: the dialog shows no error and the thread carries on.
 */

import { test, expect } from "../../fixtures/test";
import { prompt } from "../../fixtures/arcs";
import { CSRF_HEADERS, fetchUserMessageIds } from "../../fixtures/api-client";
import { LAYOUTS } from "../../fixtures/arc-layouts";
import { expectBuild } from "../../fixtures/build-checks";
import { siteOrganism } from "../../fixtures/site-reads";

const ASK_COUNT = "how many genes are in this strategy?";
const ASK_AGAIN = "and how many now?";

/** The plain echo reply for `text`, which calls no tool. */
function echoOf(text: string): RegExp {
  return new RegExp(`\\[mock\\] ${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
}

test.describe("Thread reverting", { tag: "@turn" }, () => {
  // The journey drives four turns through the worker, and one queued behind
  // another suite's build waits minutes.
  test.describe.configure({ timeout: 600_000 });

  test("a revert to an already-deleted message is a no-op the dialog does not error on", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const build = prompt(
      "single",
      `Find ${siteOrganism(siteId)} genes whose proteins have a predicted signal peptide.`,
    );
    await chatPage.startOn(siteId);
    await chatPage.sendAndSettle(build);
    const conversationId = chatPage.lastStrategyId ?? "";
    await expectBuild(page, apiClient, conversationId, siteId, LAYOUTS.single);
    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));
    await chatPage.sendTurn(ASK_AGAIN, echoOf(ASK_AGAIN));

    const messageIds = await fetchUserMessageIds(apiClient, conversationId);
    expect(messageIds).toHaveLength(3);
    const target = messageIds[1] ?? "";

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
    await expect(chatPage.userMessage(build)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessage(replacement)).toHaveCount(1);
    await expect(chatPage.userMessage(ASK_COUNT)).toHaveCount(0);
    await expect(chatPage.userMessage(ASK_AGAIN)).toHaveCount(0);
    expect(await fetchUserMessageIds(apiClient, conversationId)).toHaveLength(2);
  });
});
