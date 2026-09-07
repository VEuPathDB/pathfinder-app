import { test, expect } from "../fixtures/test";
import { entrySiteId } from "../fixtures/entry-site";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";
import type { BrowserContext, Page } from "@playwright/test";

const TASK_ID = "00000000-0000-0000-0000-0000000000bb";
const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

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

/** The turn that hands the tool to the worker: it closes at the interrupt. */
function suspendingTurn(messageId: string, toolName: string): string {
  return [
    sseFrame({
      type: "start",
      messageId,
      messageMetadata: {
        phase: "verification",
        model: "mock:deterministic",
        traceId: "mock-trace",
        createdAt: new Date().toISOString(),
      },
    }),
    sseFrame({
      type: "data-background-task-started",
      data: { taskId: TASK_ID, toolName, estimatedDurationSeconds: 5 },
    }),
    sseFrame({ type: "finish", finishReason: "other" }),
    sseDone(),
  ].join("");
}

/**
 * Serve the conversation tail. The mount reattach reads an empty tail; the
 * card's own reattach, after the turn suspends, reads the task's gap.
 */
async function routeThreadTail(page: Page, gap: string): Promise<() => number> {
  let calls = 0;
  await page.route("**/api/v1/conversations/*/events?*", async (route) => {
    calls += 1;
    if (calls === 1) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({
      status: 200,
      headers: uiMessageStreamHeaders(),
      body: gap,
    });
  });
  return () => calls;
}

async function sendPrompt(page: Page, prompt: string): Promise<void> {
  const composer = page.getByTestId("message-input");
  await expect(composer).toBeVisible({ timeout: 30_000 });
  const submit = page.getByRole("button", { name: /Send/i });
  await composer.click();
  await composer.pressSequentially(prompt, { delay: 15 });
  await expect(submit).toBeEnabled({ timeout: 15_000 });
  await composer.press("Enter");
}

test.describe("Durable task live progress", () => {
  test("the card's bar advances from the thread's own tail, not a per-task stream", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const strategyId = await openStrategy(context, siteId);

    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: uiMessageStreamHeaders(),
        body: suspendingTurn(
          "22222222-2222-2222-2222-222222222222",
          "run_control_tests_on_step",
        ),
      });
    });

    const tailCalls = await routeThreadTail(
      page,
      [
        sseFrame({
          type: "data-task-progress",
          id: TASK_ID,
          data: { taskId: TASK_ID, percent: 0.6, message: "Comparing controls" },
        }),
        sseDone(),
      ].join(""),
    );

    let perTaskRequested = false;
    await page.route(
      `**/api/v1/conversations/*/tasks/${TASK_ID}/events*`,
      async (route) => {
        perTaskRequested = true;
        await route.fulfill({ status: 204, body: "" });
      },
    );

    await page.goto(`/${siteId}/conversation/${strategyId}`);
    await sendPrompt(page, "kick off durable verification");

    const started = page.getByTestId("data-background-task-started");
    await expect(started).toBeVisible({ timeout: 20_000 });

    await expect(started.getByText("Comparing controls")).toBeVisible({
      timeout: 15_000,
    });
    await expect(started.getByText("60%")).toBeVisible({ timeout: 15_000 });
    expect(perTaskRequested).toBe(false);
    expect(tailCalls()).toBeGreaterThan(1);
  });

  test("the outcome and the continuation arrive on that same connection", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const strategyId = await openStrategy(context, siteId);

    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: uiMessageStreamHeaders(),
        body: suspendingTurn(
          "33333333-3333-3333-3333-333333333333",
          "optimize_search_parameters",
        ),
      });
    });

    await routeThreadTail(
      page,
      [
        sseFrame({
          type: "data-task-progress",
          id: TASK_ID,
          data: { taskId: TASK_ID, percent: 0.9, message: "Scoring variants" },
        }),
        sseFrame({
          type: "data-task-completed",
          data: { taskId: TASK_ID, status: "success" },
        }),
        sseFrame({ type: "start", messageId: "44444444-4444-4444-4444-444444444444" }),
        sseFrame({ type: "text-start", id: "c1" }),
        sseFrame({ type: "text-delta", id: "c1", delta: "Variant B scored best." }),
        sseFrame({ type: "text-end", id: "c1" }),
        sseFrame({ type: "finish", finishReason: "stop" }),
        sseDone(),
      ].join(""),
    );

    await page.goto(`/${siteId}/conversation/${strategyId}`);
    await sendPrompt(page, "optimize the search parameters");

    await expect(page.getByTestId("data-background-task-started")).toBeVisible({
      timeout: 20_000,
    });
    // The outcome is the task row's own state: the label names the tool, the
    // status reads Completed and the bar the row keeps is full.
    const completedTask = page.getByTestId("data-task-completed");
    await expect(completedTask.getByTestId("task-row-status")).toHaveText("Completed", {
      timeout: 15_000,
    });
    await expect(completedTask).toContainText("Optimize parameters");
    await expect(page.getByText("Variant B scored best.")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("progress-bar-fill")).toHaveAttribute(
      "style",
      /width:\s*100%/,
    );
  });
});
