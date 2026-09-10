import { test, expect } from "../fixtures/test";
import {
  fetchConversationMessages,
  fetchStoppedTurnCount,
} from "../fixtures/api-client";
import {
  MOCK_DELEGATION_DRAFT_PROMPT,
  MOCK_PLAN_PROMPT,
} from "../fixtures/mock-prompts";

/**
 * Feature: Chat — real event pipeline through Redis + PostgreSQL.
 * Mock LLM provides deterministic text, but events flow through
 * real kani orchestration → Redis streams → PostgreSQL projections.
 * Every test verifies server-side state via API.
 */
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

  test("artifact graph stores strategy plan with real WDK search names", async ({
    chatPage,
    apiClient,
  }) => {
    await chatPage.send(MOCK_PLAN_PROMPT);
    await chatPage.expectIdle();

    // Wait for strategy update — at least one assistant message rendered.
    await expect(chatPage.assistantMessages).not.toHaveCount(0, { timeout: 15_000 });

    // Fetch full strategy — verify steps were created with real WDK search names
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const fullResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(fullResp.ok()).toBeTruthy();
    const full = await fullResp.json();
    expect(full.steps.length).toBeGreaterThan(0);
    expect(full.steps[0].searchName).toBe("GenesByTaxon");
  });

  test("building executes via the structured route without chat pollution", async ({
    chatPage,
    apiClient,
    graphPage,
  }) => {
    await chatPage.send(MOCK_PLAN_PROMPT);
    await chatPage.expectIdle();
    await graphPage.expectRailPanel();

    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const fullResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(fullResp.ok()).toBeTruthy();
    const full = await fullResp.json();

    expect(full.steps.length).toBeGreaterThan(0);
    const messages = await fetchConversationMessages(apiClient, strategyId);
    expect(
      messages.some(
        (message) =>
          message.role === "user" && message.content.includes("[Plan interaction:"),
      ),
    ).toBe(false);
  });

  test("delegation draft stores event data", async ({ chatPage, apiClient }) => {
    await chatPage.send(MOCK_DELEGATION_DRAFT_PROMPT);
    await chatPage.expectIdle();

    // Messages are reconstructed from the persisted event snapshot.
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const messages = await fetchConversationMessages(apiClient, strategyId);
    expect(messages.length).toBeGreaterThan(0);
  });

  test("stop cancels the running turn and the worker closes it as stopped", async ({
    chatPage,
    page,
    apiClient,
  }) => {
    // A turn that dispatches sub-agents runs long enough to stop while it is
    // still working, which is what the server cancel answers.
    const cancelRequest = page.waitForRequest(
      (r) =>
        r.method() === "POST" &&
        /\/api\/v1\/conversations\/[^/]+\/cancel$/.test(r.url()),
      { timeout: 30_000 },
    );

    await chatPage.send(MOCK_PLAN_PROMPT);
    // The composer ignores a Stop click that lands inside the guard window a
    // double-click on Send opens, so press it once the turn reports a phase.
    await expect(page.getByTestId("assistant-status")).toHaveText(/Planning/, {
      timeout: 60_000,
    });
    await chatPage.stopStreaming();

    const req = await cancelRequest;
    const resp = await req.response();
    expect(resp).not.toBeNull();
    expect(resp?.status()).toBe(204);

    // The client ends its own stream, so the composer takes input again.
    await chatPage.expectIdle();

    // The worker reads the cancellation row and closes the turn with a
    // stopped chunk the durable log keeps.
    await expect
      .poll(async () => fetchStoppedTurnCount(apiClient, chatPage.lastStrategyId), {
        timeout: 60_000,
      })
      .toBe(1);
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
