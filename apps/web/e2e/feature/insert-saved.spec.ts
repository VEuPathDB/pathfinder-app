/**
 * The insert-saved route: a clean refusal for a saved strategy that does not
 * load or a malformed body, and a saved strategy inserted next to a step as the
 * expanded input of a new combine.
 */

import type { Page } from "@playwright/test";
import type { ConversationResponse } from "@pathfinder/shared";
import type { InsertSavedResponse } from "@pathfinder/shared/generated/types/InsertSavedResponse";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { type ApiClient, CSRF_HEADERS } from "../fixtures/api-client";
import { COMBINE_SEARCH_NAME } from "../fixtures/ast";
import { LAYOUTS, SIGNAL_PEPTIDE } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readConversation, readNodes, siteOrganism } from "../fixtures/site-reads";
import { buildOn, nodeBySearch } from "../fixtures/strategy-builds";
import { signInAsWdkAccount } from "../fixtures/wdk-account";
import type { ChatPage } from "../pages/chat.page";

/** Build the one-search strategy and return its conversation id. */
async function buildSingle(
  chatPage: ChatPage,
  page: Page,
  api: ApiClient,
  siteId: string,
): Promise<string> {
  const id = await buildOn(
    chatPage,
    siteId,
    prompt(
      "single",
      `Find ${siteOrganism(siteId)} genes whose proteins have a predicted signal peptide.`,
    ),
  );
  await expectBuild(page, api, id, siteId, LAYOUTS.single);
  return id;
}

/** The id of the step a saved strategy is inserted next to. */
async function targetStepId(api: ApiClient, conversationId: string): Promise<string> {
  return nodeBySearch(await readNodes(api, conversationId), SIGNAL_PEPTIDE).id ?? "";
}

test.describe("Insert a saved strategy", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("a saved id that does not load answers 404 and a malformed body 422", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const target = await buildSingle(chatPage, page, apiClient, siteId);
    const stepId = await targetStepId(apiClient, target);

    const notFound = await apiClient.post(
      `/api/v1/conversations/${target}/insert-saved`,
      {
        params: { siteId },
        data: {
          targetStepId: stepId,
          savedWdkStrategyId: 999_999_999,
          operator: "UNION",
        },
      },
    );
    expect(notFound.status()).toBe(404);
    expect(notFound.headers()["content-type"]).toContain("application/problem+json");
    const body = (await notFound.json()) as { code: string; status: number };
    expect(body.code).toBe("STRATEGY_NOT_FOUND");
    expect(body.status).toBe(404);

    const malformed = await apiClient.post(
      `/api/v1/conversations/${target}/insert-saved`,
      { params: { siteId }, data: { savedWdkStrategyId: 123, operator: "UNION" } },
    );
    expect(malformed.status()).toBe(422);
  });

  test("a saved strategy goes in next to a step as an expanded combine input", async ({
    page,
    chatPage,
    siteId,
  }) => {
    const ctx = page.context().request;
    await signInAsWdkAccount(ctx, siteId);
    await page.reload();

    const created: string[] = [];
    try {
      const saved = await buildSingle(chatPage, page, ctx, siteId);
      created.push(saved);
      const savedWdkStrategyId =
        (await readConversation(ctx, saved)).wdkStrategyId ?? 0;
      expect(savedWdkStrategyId).toBeGreaterThan(0);
      const marked = await ctx.patch(`/api/v1/conversations/${saved}`, {
        data: { isSaved: true },
        headers: CSRF_HEADERS,
      });
      expect(marked.status()).toBe(200);
      expect(((await marked.json()) as ConversationResponse).isSaved).toBe(true);

      const target = await buildSingle(chatPage, page, ctx, siteId);
      created.push(target);
      const before = (await readNodes(ctx, target)).length;
      const stepId = await targetStepId(ctx, target);

      const inserted = await ctx.post(`/api/v1/conversations/${target}/insert-saved`, {
        params: { siteId },
        data: { targetStepId: stepId, savedWdkStrategyId, operator: "UNION" },
        headers: CSRF_HEADERS,
      });
      expect(inserted.status(), `insert ${await inserted.text()}`).toBe(200);
      const result = (await inserted.json()) as InsertSavedResponse;
      expect(result.insertedSavedWdkStrategyId).toBe(savedWdkStrategyId);
      expect(result.combineStepId).not.toBe("");
      expect(result.wdkStrategyId).toBeGreaterThan(0);

      const after = await readNodes(ctx, target);
      expect(after.length).toBeGreaterThan(before);
      const expanded = after.filter(
        (node) =>
          node.searchName === COMBINE_SEARCH_NAME &&
          node.expandedStrategyId === savedWdkStrategyId,
      );
      expect(expanded.map((node) => node.id)).toEqual([result.combineStepId]);
      expect(expanded.map((node) => node.operator)).toEqual(["UNION"]);
    } finally {
      for (const id of created) {
        await ctx
          .delete(`/api/v1/conversations/${id}`, {
            params: { deleteFromWdk: "true" },
            headers: CSRF_HEADERS,
          })
          .catch(() => undefined);
      }
    }
  });
});
