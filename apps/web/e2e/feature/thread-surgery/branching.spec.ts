/**
 * Branching a thread: at the latest message, at an older one, and again from a
 * branch. Every turn runs through the deterministic mock provider; the fork,
 * the strategy and the transcript are the real server's.
 */

import { test, expect } from "../../fixtures/test";
import {
  type ApiClient,
  fetchConversationMessages,
  fetchUserMessageIds,
} from "../../fixtures/api-client";
import { taxonOrganism } from "./strategyState";
import {
  BUILD_ONE,
  BUILT_ORGANISM,
  EDITED_ORGANISM,
  EDIT_ORGANISM,
  RECALL,
  RECALLED,
  SITE_ID,
  SUBSTITUTED,
  VERIFIED,
  echoOf,
} from "./prompts";

interface StrategyRead {
  steps: { id: string }[];
  wdkStrategyId: number | null;
  parentConversationId: string | null;
}

async function readStrategy(
  api: ApiClient,
  conversationId: string,
): Promise<StrategyRead> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}`);
  expect(resp.status()).toBe(200);
  return (await resp.json()) as StrategyRead;
}

const ASK_COUNT = "how many genes are in this strategy?";
const ASK_AGAIN = "and how many now?";
const ASK_ONCE_MORE = "anything else worth knowing?";

test.describe("Thread branching", () => {
  // Each journey drives three to five turns through the worker, and one queued
  // behind another suite's build waits minutes.
  test.describe.configure({ timeout: 600_000 });

  test.beforeEach(async ({ chatPage, sitePicker }) => {
    await chatPage.goto();
    await sitePicker.selectSite(SITE_ID);
    await chatPage.newChat(SITE_ID);
  });

  test("a branch taken at the first turn holds exactly the pre-anchor turns", async ({
    chatPage,
    apiClient,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);

    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));

    const parentId = chatPage.lastStrategyId as string;
    const branchId = await chatPage.branchFromAssistantReply(VERIFIED);
    expect(branchId).not.toBe(parentId);

    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessages).toHaveCount(1);
    await expect(chatPage.assistantMessages).toHaveCount(1);
    await expect(chatPage.userMessage(ASK_COUNT)).toHaveCount(0);

    const branchLog = await fetchConversationMessages(apiClient, branchId);
    expect(branchLog.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(branchLog[0]?.content).toBe(BUILD_ONE);
    expect(branchLog[1]?.content).toContain("Verified end-to-end");

    // The parent keeps both of its turns.
    const parentLog = await fetchConversationMessages(apiClient, parentId);
    expect(parentLog.map((m) => m.role)).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
    ]);
  });

  test("a branch of a branch carries its own message ids and reverts on them", async ({
    chatPage,
    sidebarPage,
    apiClient,
    page,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);
    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));

    const parentId = chatPage.lastStrategyId as string;
    const childId = await chatPage.branchFromAssistantReply(VERIFIED);
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });

    await chatPage.sendTurn(ASK_AGAIN, echoOf(ASK_AGAIN));

    const grandchildId = await chatPage.branchFromAssistantReply(VERIFIED);
    expect(new Set([parentId, childId, grandchildId]).size).toBe(3);

    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });
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
    await chatPage.openEditDialog(BUILD_ONE, replacement);
    const revert = await chatPage.confirmRevert();
    expect(revert.status()).toBe(204);

    await expect(chatPage.userMessage(replacement)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.editDialogError).toHaveCount(0);
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(0);
    await expect(chatPage.userMessage(ASK_ONCE_MORE)).toHaveCount(0);
    // The revert touched the grandchild alone.
    expect(await fetchUserMessageIds(apiClient, childId)).toHaveLength(2);
  });

  test("the model answers from the branch's copied history without re-running its tools", async ({
    chatPage,
    page,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);

    await chatPage.branchFromAssistantReply(VERIFIED);
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });

    const traces = page.getByTestId("turn-trace");
    await expect(traces).toHaveCount(1, { timeout: 30_000 });

    await chatPage.sendTurn(RECALL, RECALLED);

    // The answer carries the search the pre-anchor turn framed, which only the
    // inherited Ledger knows. The reply paints in pieces, so the assertion
    // retries rather than reading the text once.
    const recall = chatPage.assistantReply(RECALLED);
    await expect(recall).toContainText("search=GenesByTaxon", { timeout: 30_000 });

    // The pre-anchor turn keeps its own trace, and the recall turn's trace is
    // the Ledger read plus the answer: it dispatched no sub-agent.
    await expect(traces).toHaveCount(2);
    await expect(recall.getByTestId("trace-row")).toHaveCount(2);
    await expect(recall.getByTestId("data-sub-agent-call")).toHaveCount(0);
    await expect(
      chatPage.assistantReply(VERIFIED).getByTestId("data-sub-agent-call"),
    ).not.toHaveCount(0);
  });

  test("a branch taken at an old message keeps that message's strategy", async ({
    chatPage,
    graphPage,
    apiClient,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);

    const parentId = chatPage.lastStrategyId as string;
    const built = await readStrategy(apiClient, parentId);
    expect(built.steps).toHaveLength(1);
    expect(await taxonOrganism(apiClient, parentId)).toEqual([BUILT_ORGANISM]);
    expect(built.wdkStrategyId).toBeGreaterThan(0);

    await chatPage.sendTurn(ASK_COUNT, echoOf(ASK_COUNT));

    await chatPage.sendTurn(EDIT_ORGANISM, SUBSTITUTED);

    await chatPage.sendTurn(ASK_AGAIN, echoOf(ASK_AGAIN));

    // The later turn did edit the strategy the thread holds now.
    const edited = await readStrategy(apiClient, parentId);
    expect(await taxonOrganism(apiClient, parentId)).toEqual([EDITED_ORGANISM]);

    // Anchor on the reply of the second turn, which is unique in this thread.
    const branchId = await chatPage.branchFromAssistantReply(echoOf(ASK_COUNT));
    await expect(chatPage.userMessage(BUILD_ONE)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessage(EDIT_ORGANISM)).toHaveCount(0);

    // The branch carries the strategy as it stood at the anchor, not the edit.
    const branch = await readStrategy(apiClient, branchId);
    expect(await taxonOrganism(apiClient, branchId)).toEqual([BUILT_ORGANISM]);
    expect(branch.steps).toHaveLength(1);
    expect(branch.parentConversationId).toBe(parentId);
    // The branch owns a WDK strategy of its own.
    expect(branch.wdkStrategyId).toBeGreaterThan(0);
    expect(branch.wdkStrategyId).not.toBe(edited.wdkStrategyId);
    expect(branch.wdkStrategyId).not.toBe(built.wdkStrategyId);

    // The rail lists the branch's own single step.
    await graphPage.openRailStrategyPanel();
    expect(await graphPage.railStepCount()).toBe(1);
    await expect(graphPage.railFooter).toContainText("1 step");
  });
});
