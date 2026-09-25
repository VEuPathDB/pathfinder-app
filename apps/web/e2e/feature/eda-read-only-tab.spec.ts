/**
 * Journey 2: the tab shows the analysis the conversation built, and the site
 * is where it is edited.
 *
 * A turn states the analysis the agent's compute produced. The tab then reads
 * the same analysis, shows it as text and a figure, offers no editing control,
 * and links the site's own page for it. A second load reads the document again.
 */

import type { BrowserContext, Page } from "@playwright/test";

import { test, expect, BASE_URL } from "../fixtures/test";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";
import { CSRF_HEADERS } from "../fixtures/api-client";
import {
  ANALYSIS_URL,
  COMPARED_ANALYSIS,
  COMPARISON_SENTENCE,
  edaJson,
  FEBRILE_SUMMARY,
  routeEdaReads,
  SITE_ID,
  STUDY_TITLE,
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

/** The turn in which the agent's compute states the analysis and its figure. */
async function routeComputeTurn(page: Page): Promise<void> {
  const stream = [
    sseFrame({
      type: "start",
      messageId: "44444444-4444-4444-4444-444444444444",
      messageMetadata: {
        phase: "frame",
        model: "mock:deterministic",
        traceId: "mock-eda-read-only",
        createdAt: new Date().toISOString(),
      },
    }),
    sseFrame({ type: "data-eda.analysis-state", data: COMPARED_ANALYSIS }),
    sseFrame({ type: "data-eda.viz", data: VOLCANO_VIZ }),
    sseFrame({ type: "finish", finishReason: "stop" }),
    sseDone(),
  ].join("");
  await page.route("**/api/v1/chat", (route) =>
    route.fulfill({ status: 200, headers: uiMessageStreamHeaders(), body: stream }),
  );
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

test.describe("The EDA tab reads the analysis and the site edits it", () => {
  test("the tab shows the compute the agent ran, read-only, with the site's link", async ({
    page,
    context,
  }) => {
    const conversationId = await openConversation(context);
    await routeEdaReads(page);
    await routeComputeTurn(page);
    await page.route(`**/api/v1/conversations/${conversationId}/eda`, (route) =>
      route.fulfill(edaJson({ analysis: COMPARED_ANALYSIS })),
    );

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await sendTurn(page, "compare febrile and normal samples");
    await expect(page.getByTestId("data-eda-analysis-state")).toBeVisible({
      timeout: 20_000,
    });

    // The dev server compiles the tab route on first request.
    await page.getByRole("button", { name: "Open study", exact: true }).click();
    await expect(page).toHaveURL(
      new RegExp(`/${SITE_ID}/conversation/${conversationId}/eda$`),
      { timeout: 60_000 },
    );

    const tab = page.getByTestId("eda-workbench");
    await expect(tab.getByTestId("eda-workbench-title")).toContainText(STUDY_TITLE, {
      timeout: 30_000,
    });
    await expect(tab.getByTestId("eda-filter-chip-0")).toHaveText(FEBRILE_SUMMARY);
    await expect(tab.getByTestId("eda-entity-count-ENT_8151325d")).toHaveText(
      "6 of 12 Sample",
    );
    await expect(tab.getByTestId("eda-comparison-sentence")).toHaveText(
      COMPARISON_SENTENCE,
    );
    await expect(tab.getByTestId("eda-viz-volcano").locator("canvas")).toBeVisible();
    await expect(tab.getByTestId("eda-volcano-cut")).toHaveText(
      "Higher in either group, |effect size| >= 1, p <= 0.05",
    );
    await expect(tab.getByTestId("eda-volcano-selection")).toHaveText(
      "1 gene selected, 1 of 3 retained by the comparison",
    );

    await expect(tab.locator("input, select, textarea")).toHaveCount(0);
    const siteLink = tab.getByRole("link", { name: "Open in PlasmoDB" });
    await expect(siteLink).toHaveAttribute("href", ANALYSIS_URL);
    await expect(siteLink).toHaveAttribute("target", "_blank");
    await expect(tab.getByTestId("eda-workbench-header")).toContainText(
      "Edit on PlasmoDB; this tab shows what the site holds.",
    );
  });

  test("a reload shows the subset the site holds now", async ({ page, context }) => {
    const conversationId = await openConversation(context);
    await routeEdaReads(page);
    const edited = {
      ...COMPARED_ANALYSIS,
      filterSummaries: ["temperature_condition is normal"],
    };
    // The researcher edits the subset on the site between the two loads.
    let siteEdited = false;
    await page.route(`**/api/v1/conversations/${conversationId}/eda`, (route) =>
      route.fulfill(edaJson({ analysis: siteEdited ? edited : COMPARED_ANALYSIS })),
    );

    await page.goto(`/${SITE_ID}/conversation/${conversationId}/eda`);
    const chip = page.getByTestId("eda-workbench").getByTestId("eda-filter-chip-0");
    await expect(chip).toHaveText(FEBRILE_SUMMARY, { timeout: 60_000 });

    siteEdited = true;
    await page.reload();
    await expect(chip).toBeVisible({ timeout: 60_000 });
    await expect(chip).toHaveText("temperature_condition is normal", {
      timeout: 60_000,
    });
  });
});
