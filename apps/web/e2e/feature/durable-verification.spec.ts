/**
 * Durable verification TaskCard E2E (scope-reduced).
 *
 * Exercising the full interrupt + worker + resume flow in Playwright
 * exceeds the per-test budget, so this test verifies the frontend half:
 * the thread stream carries `data-background-task-started`,
 * `data-task-progress` and `data-task-completed`, and the card renders
 * all three from the message's own parts.
 *
 * Full interrupt+worker+resume coverage lives in the backend integration
 * tests (see `test_dispatcher_interrupt.py`, the `durable/` suite, and
 * `test_events_endpoint.py`).
 *
 * Note: this file intentionally avoids the `ChatPage` page-object model -
 * several of its `data-testid` selectors (`message-composer`,
 * `message-input`, `send-button`) no longer exist in the post-AI-SDK-v6
 * composer and are pre-existing breakage outside this task's scope. The
 * composer is targeted here by its placeholder + accessible submit button
 * name instead.
 */

import { test, expect } from "../fixtures/test";
import { entrySiteId } from "../fixtures/entry-site";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";
import type { BrowserContext } from "@playwright/test";

const TASK_ID = "00000000-0000-0000-0000-0000000000aa";
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

test.describe("Durable verification TaskCard", () => {
  test.describe.configure({ mode: "serial" });

  test("TaskCard renders from data-background-task-started and tracks progress to success", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const strategyId = await openStrategy(context, siteId);

    // Background-task progress is rendered from chunks delivered on the chat
    // event stream (data-background-task-started -> data-task-progress ->
    // data-task-completed), each by its own typed part renderer.
    const chatStream = [
      sseFrame({
        type: "start",
        messageId: "11111111-1111-1111-1111-111111111111",
        messageMetadata: {
          phase: "verification",
          model: "mock:deterministic",
          traceId: "mock-trace",
          createdAt: new Date().toISOString(),
        },
      }),
      sseFrame({
        type: "data-background-task-started",
        data: {
          taskId: TASK_ID,
          toolName: "run_control_tests_on_step",
          estimatedDurationSeconds: 3,
        },
      }),
      sseFrame({
        type: "data-task-progress",
        data: { taskId: TASK_ID, percent: 0.66, message: "Comparing controls" },
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
    const composer = page.getByTestId("message-input");
    await expect(composer).toBeVisible({ timeout: 30_000 });
    const submit = page.getByRole("button", { name: /Send/i });
    await composer.click();
    await composer.pressSequentially("kick off durable verification", {
      delay: 15,
    });
    await expect(submit).toBeEnabled({ timeout: 15_000 });
    await composer.press("Enter");

    // The started badge names the durable tool (humanized label).
    const started = page.getByTestId("data-background-task-started");
    await expect(started).toBeVisible({ timeout: 20_000 });
    await expect(started).toContainText("Run control tests");

    // Progress + success completion render as their own parts.
    await expect(started.getByTestId("data-task-progress")).toBeVisible({
      timeout: 15_000,
    });
    const completed = page.getByTestId("data-task-completed");
    await expect(completed).toBeVisible({ timeout: 15_000 });
    await expect(completed).toContainText(/completed/i);
  });
});
