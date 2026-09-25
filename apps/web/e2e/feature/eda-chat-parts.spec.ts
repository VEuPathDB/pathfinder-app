/**
 * Journey 1: an exploration turn draws the EDA cards in the thread.
 *
 * The chat turn is route-mocked the way durable-verification.spec.ts mocks it,
 * so the LLM is the only mocked thing here. Each test opens its own
 * conversation, because the mocked tail's [DONE] cursor is persisted per
 * thread.
 */

import type { BrowserContext, Page } from "@playwright/test";

import { test, expect, BASE_URL } from "../fixtures/test";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";
import { CSRF_HEADERS } from "../fixtures/api-client";
import {
  analysisState,
  edaJson,
  FEBRILE_SUMMARY,
  FILTERED_ANALYSIS,
  SITE_ID,
  STUDY_TITLE,
  SUBSET_PREVIEW,
  VOLCANO_VIZ,
} from "../fixtures/eda";

async function openConversation(context: BrowserContext): Promise<string> {
  const response = await context.request.post(`${BASE_URL}/api/v1/conversations/open`, {
    data: { siteId: SITE_ID },
    headers: CSRF_HEADERS,
  });
  if (!response.ok()) throw new Error(`open failed: ${response.status()}`);
  const body = (await response.json()) as { conversationId?: string; id?: string };
  const id = body.conversationId ?? body.id;
  if (id === undefined || id === "") throw new Error("open returned no id");
  return id;
}

async function sendTurn(page: Page, text: string): Promise<void> {
  const composer = page.getByTestId("message-input");
  await expect(composer).toBeVisible({ timeout: 30_000 });
  await composer.click();
  await composer.pressSequentially(text, { delay: 15 });
  await expect(page.getByRole("button", { name: /Send/i })).toBeEnabled({
    timeout: 15_000,
  });
  await composer.press("Enter");
}

test.describe("EDA data parts render in the thread", () => {
  test("an exploration turn draws the chips, the counts and the volcano", async ({
    page,
    context,
  }) => {
    const conversationId = await openConversation(context);

    const stream = [
      sseFrame({
        type: "start",
        messageId: "22222222-2222-2222-2222-222222222222",
        messageMetadata: {
          phase: "frame",
          model: "mock:deterministic",
          traceId: "mock-eda-trace",
          createdAt: new Date().toISOString(),
        },
      }),
      sseFrame({ type: "data-eda.analysis-state", data: FILTERED_ANALYSIS }),
      sseFrame({ type: "data-eda.subset-preview", data: SUBSET_PREVIEW }),
      sseFrame({ type: "data-eda.viz", data: VOLCANO_VIZ }),
      sseFrame({ type: "finish", finishReason: "stop" }),
      sseDone(),
    ].join("");

    await page.route("**/api/v1/chat", (route) =>
      route.fulfill({ status: 200, headers: uiMessageStreamHeaders(), body: stream }),
    );

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await sendTurn(page, "explore the heat shock study");

    // 6 of 12 samples: the febrile half of the recorded entity counts.
    const card = page.getByTestId("data-eda-analysis-state");
    await expect(card).toBeVisible({ timeout: 20_000 });
    await expect(card).toContainText(STUDY_TITLE);
    await expect(card).toContainText("6 of 12 Sample");
    await expect(card).toContainText("34,320 of 68,640 pfal3D7 htseq counts");
    await expect(page.getByTestId("data-eda-filter-chip-0")).toContainText(
      FEBRILE_SUMMARY,
    );

    const preview = page.getByTestId("data-eda-subset-preview");
    await expect(preview).toContainText("6 of 12 Sample");
    await expect(page.getByTestId("data-eda-subset-histogram")).toBeVisible();
    await expect(page.getByTestId("data-eda-subset-bin-0")).toContainText("febrile 6");
    await expect(page.getByTestId("data-eda-subset-coverage")).toContainText(
      "6 of 6 records have a value",
    );

    // One of the three points clears both thresholds; one carries no p-value.
    const volcano = page.getByTestId("eda-viz-volcano");
    await expect(volcano).toBeVisible();
    await expect(volcano.locator("canvas")).toBeVisible();
    await expect(page.getByTestId("eda-viz-volcano-selection")).toContainText(
      "1 gene selected at these thresholds - 1 of 3 retained by the comparison",
    );
    await expect(page.getByTestId("eda-viz-volcano-genes")).toContainText(
      "PF3D7_0100200",
    );
    await expect(page.getByTestId("eda-viz-volcano-dropped")).toContainText(
      "1 point without a p-value was not plotted",
    );
  });

  test("the rail marks the EDA panel and opens the tab", async ({ page, context }) => {
    const conversationId = await openConversation(context);
    const stream = [
      sseFrame({
        type: "start",
        messageId: "33333333-3333-3333-3333-333333333333",
        messageMetadata: {
          phase: "frame",
          model: "mock:deterministic",
          traceId: "mock-eda-trace-2",
          createdAt: new Date().toISOString(),
        },
      }),
      sseFrame({ type: "data-eda.analysis-state", data: analysisState() }),
      sseFrame({ type: "finish", finishReason: "stop" }),
      sseDone(),
    ].join("");
    await page.route("**/api/v1/chat", (route) =>
      route.fulfill({ status: 200, headers: uiMessageStreamHeaders(), body: stream }),
    );
    // The tab hydrates from the binding read, which the rail entry navigates to.
    await page.route(`**/api/v1/conversations/${conversationId}/eda`, (route) =>
      route.fulfill(edaJson({ analysis: analysisState() })),
    );

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await sendTurn(page, "open the heat shock study");

    await expect(page.getByTestId("data-eda-analysis-state")).toBeVisible({
      timeout: 20_000,
    });

    // The rail auto-opens the Progress panel on the first user message, so the
    // Studies toggle reads "Open Studies" until it is clicked.
    await page.getByRole("button", { name: /^(Open|Close) Studies$/ }).click();
    await expect(page.getByTestId("rail-eda-panel")).toContainText(STUDY_TITLE);
    await expect(page.getByTestId("rail-eda-panel")).toContainText(
      "0 filters - 0 computations",
    );

    // The dev server compiles the tab route on first request, so the
    // navigation assertion waits longer than the default.
    await page.getByTestId("rail-eda-open").click();
    await expect(page).toHaveURL(
      new RegExp(`/${SITE_ID}/conversation/${conversationId}/eda$`),
      { timeout: 60_000 },
    );
    await expect(page.getByTestId("eda-workbench-header")).toContainText(STUDY_TITLE, {
      timeout: 30_000,
    });
  });

  test("the analysis card opens the tab on the same analysis", async ({
    page,
    context,
  }) => {
    const conversationId = await openConversation(context);
    const stream = [
      sseFrame({
        type: "start",
        messageId: "55555555-5555-5555-5555-555555555555",
        messageMetadata: {
          phase: "frame",
          model: "mock:deterministic",
          traceId: "mock-eda-trace-3",
          createdAt: new Date().toISOString(),
        },
      }),
      sseFrame({ type: "data-eda.analysis-state", data: FILTERED_ANALYSIS }),
      sseFrame({ type: "finish", finishReason: "stop" }),
      sseDone(),
    ].join("");
    await page.route("**/api/v1/chat", (route) =>
      route.fulfill({ status: 200, headers: uiMessageStreamHeaders(), body: stream }),
    );
    await page.route(`**/api/v1/conversations/${conversationId}/eda`, (route) =>
      route.fulfill(edaJson({ analysis: FILTERED_ANALYSIS })),
    );

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await sendTurn(page, "explore the heat shock study");

    await expect(page.getByTestId("data-eda-analysis-state")).toBeVisible({
      timeout: 20_000,
    });
    // The dev server compiles the tab route on first request, so the
    // navigation assertion waits longer than the default.
    await page.getByRole("button", { name: "Open study", exact: true }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${SITE_ID}/conversation/${conversationId}/eda$`),
      { timeout: 60_000 },
    );
    await expect(page.getByTestId("eda-workbench-title")).toContainText(STUDY_TITLE, {
      timeout: 30_000,
    });
  });
});
