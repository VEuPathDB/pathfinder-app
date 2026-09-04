/**
 * A build request on a thread that already has a strategy is refused, the
 * reply routes the user to an edit, and the existing strategy is untouched.
 */

import { test, expect } from "../../fixtures/test";
import { BUILD_ONE, SITE_ID, VERIFIED } from "./prompts";

test.describe("Build refusal", () => {
  test.describe.configure({ timeout: 600_000 });

  test.beforeEach(async ({ chatPage, sitePicker }) => {
    await chatPage.goto();
    await sitePicker.selectSite(SITE_ID);
    await chatPage.newChat(SITE_ID);
  });

  test("a second build answers the refusal and keeps the strategy", async ({
    chatPage,
    apiClient,
  }) => {
    await chatPage.sendTurn(BUILD_ONE, VERIFIED);
    const conversationId = chatPage.lastStrategyId;
    expect(conversationId).toBeTruthy();
    const before = await apiClient.get(
      `/api/v1/conversations/${conversationId as string}/ast`,
    );
    const beforeAst = (await before.json()) as { root: unknown };

    await chatPage.sendTurn(
      "Build a comprehensive kinase strategy",
      /Nothing was built/,
    );
    await chatPage.expectAssistantMessage(/edit_strategy/);

    const after = await apiClient.get(
      `/api/v1/conversations/${conversationId as string}/ast`,
    );
    expect(after.status()).toBe(200);
    const afterAst = (await after.json()) as { root: unknown };
    expect(afterAst.root).toEqual(beforeAst.root);
  });
});
