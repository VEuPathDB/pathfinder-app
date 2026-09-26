/**
 * Branching a branch: every copy carries message ids of its own, and a revert
 * inside the grandchild names the grandchild's ids. Only the model is mocked.
 */

import { test, expect } from "../../fixtures/test";
import { prompt } from "../../fixtures/arcs";
import {
  fetchConversationMessages,
  fetchUserMessageIds,
} from "../../fixtures/api-client";
import { LAYOUTS } from "../../fixtures/arc-layouts";
import { expectBuild } from "../../fixtures/build-checks";
import { siteOrganism, strategyCaption } from "../../fixtures/site-reads";

const ASK_COUNT = "how many genes are in this strategy?";
const ASK_AGAIN = "and how many now?";
const ASK_ONCE_MORE = "anything else worth knowing?";

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The plain echo reply for `text`, which calls no tool. */
function echoOf(text: string): RegExp {
  return new RegExp(`\\[mock\\] ${escapeRegExp(text)}`);
}

test.describe("Thread branching", { tag: "@turn" }, () => {
  // The journey drives five turns through the worker, and one queued behind
  // another suite's build waits minutes.
  test.describe.configure({ timeout: 600_000 });

  test("a branch of a branch carries its own message ids and reverts on them", async ({
    chatPage,
    sidebarPage,
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
    const parentId = chatPage.lastStrategyId ?? "";
    const counts = await expectBuild(page, apiClient, parentId, siteId, LAYOUTS.single);
    // The build reply is the only one that carries its figure's caption.
    const built = new RegExp(
      escapeRegExp(strategyCaption(LAYOUTS.single.steps, counts.root)),
    );
    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));

    const childId = await chatPage.branchFromAssistantReply(built);
    await expect(chatPage.userMessage(build)).toHaveCount(1, { timeout: 30_000 });

    await chatPage.sendTurn(ASK_AGAIN, echoOf(ASK_AGAIN));

    const grandchildId = await chatPage.branchFromAssistantReply(built);
    expect(new Set([parentId, childId, grandchildId]).size).toBe(3);

    await expect(chatPage.userMessage(build)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessages).toHaveCount(1);
    await expect(chatPage.userMessage(ASK_AGAIN)).toHaveCount(0);

    const grandchildLog = await fetchConversationMessages(apiClient, grandchildId);
    expect(grandchildLog.map((m) => m.role)).toEqual(["user", "assistant"]);

    // Every copy is a fresh row: no id is shared with an ancestor.
    const parentIds = await fetchUserMessageIds(apiClient, parentId);
    const childIds = await fetchUserMessageIds(apiClient, childId);
    const grandchildIds = await fetchUserMessageIds(apiClient, grandchildId);
    expect(parentIds).toHaveLength(2);
    expect(childIds).toHaveLength(2);
    expect(grandchildIds).toHaveLength(1);
    const everyId = [...parentIds, ...childIds, ...grandchildIds];
    expect(new Set(everyId).size).toBe(everyId.length);

    // The sidebar lists both branches under the thread they came from.
    await sidebarPage.refresh();
    await expect(sidebarPage.item(parentId)).toBeVisible({ timeout: 15_000 });
    const subtree = page.getByTestId("subtree-item");
    await expect(
      subtree.filter({ has: page.locator(`[href$="/conversation/${childId}"]`) }),
    ).toHaveCount(1, { timeout: 15_000 });
    await expect(
      subtree.filter({ has: page.locator(`[href$="/conversation/${grandchildId}"]`) }),
    ).toHaveCount(1);

    // Reverting inside the grandchild names the grandchild's own message id.
    await chatPage.sendTurn(ASK_ONCE_MORE, echoOf(ASK_ONCE_MORE));

    const replacement = "start over from scratch here";
    await chatPage.openEditDialog(build, replacement);
    const revert = await chatPage.confirmRevert();
    expect(revert.status()).toBe(204);

    await expect(chatPage.userMessage(replacement)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.editDialogError).toHaveCount(0);
    await expect(chatPage.userMessage(build)).toHaveCount(0);
    await expect(chatPage.userMessage(ASK_ONCE_MORE)).toHaveCount(0);
    // The revert touched the grandchild alone.
    expect(await fetchUserMessageIds(apiClient, childId)).toHaveLength(2);
  });
});
