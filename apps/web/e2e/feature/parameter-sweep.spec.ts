/**
 * Parameter sweep E2E test.
 *
 * The durable-task lifecycle applied to `optimize_search_parameters`: the
 * thread carries the started chunk, the task's progress and its outcome, and
 * the card renders all three from the message's own parts.
 */

import { test, expect } from "../fixtures/test";
import { entrySiteId } from "../fixtures/entry-site";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";
import type { BrowserContext } from "@playwright/test";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
const TASK_ID = "00000000-0000-0000-0000-sweep0000001";

interface OpenStrategyResponse {
  conversationId?: string;
  strategyId?: string;
  id?: string;
}

async function openStrategy(context: BrowserContext, siteId: string): Promise<string> {
  const resp = await context.request.post(`${BASE_URL}/api/v1/conversations/open`, {
    data: { siteId },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!resp.ok()) {
    throw new Error(`openStrategy failed: ${resp.status()}`);
  }
  const body = (await resp.json()) as OpenStrategyResponse;
  const id = body.conversationId ?? body.strategyId ?? body.id;
  if (id === undefined || id === "") {
    throw new Error("openStrategy returned no id");
  }
  return id;
}

test.describe("Parameter Sweep", () => {
  test.describe.configure({ mode: "serial" });

  test("optimize_search_parameters task renders progress and completes", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const strategyId = await openStrategy(context, siteId);

    const chatStream = [
      sseFrame({
        type: "start",
        messageId: "22222222-2222-2222-2222-222222222222",
      }),
      sseFrame({ type: "text-start", id: "t1" }),
      sseFrame({
        type: "text-delta",
        id: "t1",
        delta: "Starting parameter optimization...",
      }),
      sseFrame({ type: "text-end", id: "t1" }),
      sseFrame({
        type: "data-background-task-started",
        data: {
          taskId: TASK_ID,
          toolName: "optimize_search_parameters",
          estimatedDurationSeconds: 3,
        },
      }),
      sseFrame({
        type: "data-task-progress",
        data: { taskId: TASK_ID, percent: 0.6, message: "Testing variant 3/5" },
      }),
      sseFrame({
        type: "data-task-completed",
        data: { taskId: TASK_ID, status: "success" },
      }),
      sseFrame({ type: "finish", finishReason: "stop" }),
      sseDone(),
    ].join("");

    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: uiMessageStreamHeaders(),
        body: chatStream,
      });
    });

    await page.goto(`/${siteId}/conversation/${strategyId}`);
    const composer = page.getByPlaceholder("Ask about strategies", {
      exact: false,
    });
    await expect(composer).toBeVisible({ timeout: 30_000 });

    await composer.click();
    await composer.pressSequentially("Optimize search parameters with 5 variants", {
      delay: 15,
    });
    const sendButton = page.getByRole("button", { name: /Send/i });
    await expect(sendButton).toBeEnabled({ timeout: 15_000 });
    await composer.press("Enter");

    await expect(page.getByText("Starting parameter optimization...")).toBeVisible({
      timeout: 30_000,
    });

    const started = page.getByTestId("data-background-task-started");
    await expect(started).toBeVisible({ timeout: 15_000 });
    await expect(started).toContainText(/optimize parameters/i);
    await expect(started.getByTestId("data-task-progress")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("data-task-completed")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("chat stream delivers assistant response for sweep request", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const strategyId = await openStrategy(context, siteId);

    const chatStream = [
      sseFrame({
        type: "start",
        messageId: "33333333-3333-3333-3333-333333333333",
      }),
      sseFrame({ type: "text-start", id: "t1" }),
      sseFrame({
        type: "text-delta",
        id: "t1",
        delta: "[mock] optimize search parameters with 5 variants",
      }),
      sseFrame({ type: "text-end", id: "t1" }),
      sseFrame({ type: "finish", finishReason: "stop" }),
      sseDone(),
    ].join("");

    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: uiMessageStreamHeaders(),
        body: chatStream,
      });
    });

    await page.goto(`/${siteId}/conversation/${strategyId}`);
    const composer = page.getByPlaceholder("Ask about strategies", {
      exact: false,
    });
    await expect(composer).toBeVisible({ timeout: 30_000 });

    await composer.click();
    await composer.pressSequentially("optimize search parameters with 5 variants", {
      delay: 15,
    });
    const sendButton = page.getByRole("button", { name: /Send/i });
    await expect(sendButton).toBeEnabled({ timeout: 15_000 });
    await composer.press("Enter");

    await expect(
      page.getByText("[mock] optimize search parameters with 5 variants"),
    ).toBeVisible({ timeout: 30_000 });
  });
});
