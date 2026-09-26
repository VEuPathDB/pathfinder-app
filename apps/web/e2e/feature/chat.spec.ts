/**
 * Chat turns persist through the durable event log: echo turns, and builds
 * whose steps carry the site's own search names.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { fetchConversationMessages } from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { readConversation, siteOrganism } from "../fixtures/site-reads";

test.describe("Chat", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("send message stores conversation in PostgreSQL", async ({
    chatPage,
    apiClient,
  }) => {
    await chatPage.send("hello persistence");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    // Messages are reconstructed from the persisted event snapshot.
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const messages = await fetchConversationMessages(apiClient, strategyId);
    expect(messages.length).toBeGreaterThan(0);
  });

  test("empty message keeps send button disabled", async ({ chatPage }) => {
    await chatPage.expectSendDisabled();
  });

  test("multiple messages stored sequentially in conversation", async ({
    chatPage,
    apiClient,
  }) => {
    await chatPage.send("first message");
    await chatPage.expectAssistantMessage(/\[mock\].*first message/);
    await chatPage.expectIdle();

    await chatPage.send("second message");
    await chatPage.expectAssistantMessage(/\[mock\].*second message/);
    await chatPage.expectIdle();

    // Verify both messages persisted (use captured ID)
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const messages = await fetchConversationMessages(apiClient, strategyId);
    const userMsgs = messages.filter((m) => m.role === "user");
    const assistantMsgs = messages.filter((m) => m.role === "assistant");
    expect(userMsgs.length).toBeGreaterThanOrEqual(2);
    expect(assistantMsgs.length).toBeGreaterThanOrEqual(2);
  });

  test("conversation auto-created and persisted", async ({ chatPage, sidebarPage }) => {
    await chatPage.send("hello world");
    await chatPage.expectAssistantMessage(/\[mock\]/);

    await sidebarPage.expectAtLeastOneConversation();

    // Strategy ID was captured during newChat
    expect(chatPage.lastStrategyId).toBeTruthy();
  });

  test("page reload restores conversation from PostgreSQL", async ({
    chatPage,
    page,
    apiClient,
  }) => {
    await chatPage.send("persistent message");
    await chatPage.expectAssistantMessage(/\[mock\].*persistent message/);

    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();

    await page.reload();
    await expect(page.getByTestId("message-composer")).toBeVisible();
    await expect(page.getByText("persistent message", { exact: true })).toBeVisible({
      timeout: 15_000,
    });

    // Strategy still exists after reload
    const afterResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(afterResp.ok()).toBeTruthy();
  });
});

test.describe("Chat builds", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  const buildMessage = (siteId: string) =>
    prompt(
      "single",
      `Find ${siteOrganism(siteId)} genes whose proteins have a predicted signal peptide.`,
    );

  test("artifact graph stores strategy plan with real WDK search names", async ({
    chatPage,
    apiClient,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    await chatPage.sendAndSettle(buildMessage(siteId));

    const conversationId = chatPage.lastStrategyId ?? "";
    await expect
      .poll(async () =>
        ((await readConversation(apiClient, conversationId)).steps ?? []).map(
          (step) => step.searchName,
        ),
      )
      .toEqual(LAYOUTS.single.searches);
  });

  test("building executes via the structured route without chat pollution", async ({
    chatPage,
    apiClient,
    graphPage,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    await chatPage.sendAndSettle(buildMessage(siteId));
    await graphPage.expectRailPanel();

    const conversationId = chatPage.lastStrategyId ?? "";
    const full = await readConversation(apiClient, conversationId);
    expect(full.steps ?? []).toHaveLength(LAYOUTS.single.steps);
    const messages = await fetchConversationMessages(apiClient, conversationId);
    expect(
      messages.some(
        (message) =>
          message.role === "user" && message.content.includes("[Plan interaction:"),
      ),
    ).toBe(false);
  });
});
