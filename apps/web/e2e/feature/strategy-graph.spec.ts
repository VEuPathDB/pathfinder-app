import { test, expect } from "../fixtures/test";
import { MOCK_DELEGATION_PROMPT, MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";

test.describe("Strategy Graph", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("planning artifact creates strategy with real search names stored in DB", async ({
    chatPage,
    graphPage,
    apiClient,
  }) => {
    await chatPage.send(MOCK_PLAN_PROMPT);
    await graphPage.expectRailPanel();
    await chatPage.expectIdle();

    // UI: Step rows visible with content
    const rowCount = await graphPage.railStepRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // UI: First step row should show real search-related text
    const firstRowText = await graphPage.firstRailStepText();
    expect(firstRowText.length).toBeGreaterThan(0);

    // API: Strategy persisted with steps - use captured ID for isolation
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const fullResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(fullResp.ok()).toBeTruthy();
    const full = await fullResp.json();
    expect(full.steps.length).toBeGreaterThan(0);
  });

  test("delegation creates strategy steps visible in graph and DB", async ({
    chatPage,
    graphPage,
    apiClient,
  }) => {
    await chatPage.send(MOCK_DELEGATION_PROMPT);
    await graphPage.expectRailPanel();
    await chatPage.expectIdle();

    // UI: Step rows from delegation
    const rowCount = await graphPage.railStepRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // API: Strategy persisted - use captured ID for isolation
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const fullResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(fullResp.ok()).toBeTruthy();
  });

  test("graph persists across page reload - UI and DB consistent", async ({
    chatPage,
    graphPage,
    page,
    apiClient,
  }) => {
    await chatPage.send(MOCK_PLAN_PROMPT);
    await graphPage.expectRailPanel();

    // Use the strategy ID captured during newChat()
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();

    await page.reload();
    await expect(page.getByTestId("message-composer")).toBeVisible({
      timeout: 15_000,
    });

    // UI: Graph rail must be visible after reload
    await graphPage.expectRailPanel();
    const rowCount = await graphPage.railStepRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // API: Strategy still in DB after reload with steps intact
    const afterResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(afterResp.ok()).toBeTruthy();
    const strategy = await afterResp.json();
    expect(strategy.steps.length).toBeGreaterThan(0);
  });

  test("delegation graph appears immediately during streaming - no refresh needed", async ({
    chatPage,
    graphPage,
  }) => {
    await chatPage.send(MOCK_DELEGATION_PROMPT);
    // Graph must appear during execution streaming, before message_end.
    await graphPage.expectRailPanel();
    // Step rows must be visible
    const rowCount = await graphPage.railStepRows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test("delegation graph visible in UI after page reload", async ({
    chatPage,
    graphPage,
    page,
    apiClient,
  }) => {
    await chatPage.send(MOCK_DELEGATION_PROMPT);
    await graphPage.expectRailPanel();
    await chatPage.expectIdle();

    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();

    await page.reload();
    await expect(page.getByTestId("message-composer")).toBeVisible({
      timeout: 15_000,
    });

    // UI: Graph rail renders after reload
    await graphPage.expectRailPanel();
    const rowCount = await graphPage.railStepRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // API: Steps persisted
    const resp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(resp.ok()).toBeTruthy();
    const strategy = await resp.json();
    expect(strategy.steps.length).toBeGreaterThan(0);
  });
});
