/**
 * Journey 3: the figure of the agent's compute exports a step the strategy
 * rail lists. The export and the conversation read are answered in the
 * browser: the first read answers only after the export, with the strategy
 * before it, and a later read returns the exported strategy.
 */

import type { BrowserContext } from "@playwright/test";

import { test, expect, BASE_URL } from "../fixtures/test";
import { CSRF_HEADERS } from "../fixtures/api-client";
import {
  COMPARED_ANALYSIS,
  edaJson,
  EXPORTED_STEP,
  exportedStrategy,
  routeEdaReads,
  SITE_ID,
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

test.describe("EDA export as a strategy step", () => {
  test("the figure of a compute exports a step the strategy rail lists", async ({
    page,
    context,
  }) => {
    const conversationId = await openConversation(context);
    await routeEdaReads(page);

    let exported = false;
    let answerExport = (): void => undefined;
    const exportAnswered = new Promise<void>((resolve) => {
      answerExport = resolve;
    });
    await page.route(`**/api/v1/conversations/${conversationId}`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      if (exported) {
        await route.fulfill(edaJson(exportedStrategy(conversationId)));
        return;
      }
      // The read that began before the export answers after it, with no step.
      await exportAnswered;
      await route.continue();
    });

    const actions: { action: string; thresholds?: unknown }[] = [];
    await page.route(`**/api/v1/conversations/${conversationId}/eda`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill(edaJson({ analysis: COMPARED_ANALYSIS }));
        return;
      }
      const body = route.request().postDataJSON() as {
        action: string;
        thresholds?: unknown;
      };
      actions.push(body);
      exported = true;
      await route.fulfill(
        edaJson({
          analysis: { ...COMPARED_ANALYSIS, revision: 3 },
          step: exportedStrategy(conversationId),
        }),
      );
      answerExport();
    });

    await page.goto(`/${SITE_ID}/conversation/${conversationId}/eda`);
    await expect(page.getByTestId("eda-viz-volcano")).toBeVisible({ timeout: 60_000 });

    const exportButton = page.getByRole("button", { name: "Export as step" });
    await expect(exportButton).toBeEnabled({ timeout: 20_000 });
    await exportButton.click();

    // The exported step is the only root, so it begins the strategy.
    await expect(page.getByTestId("eda-export-began-strategy")).toContainText(
      "This step is now the strategy's first step.",
    );
    await expect(page.getByTestId("eda-export-step-name")).toHaveText(
      `Exported: ${EXPORTED_STEP.displayName}`,
    );
    // The export names the volcano; the server writes the cut the analysis stores.
    expect(actions).toEqual([{ action: "export-step", source: "volcano" }]);

    await page
      .locator(`[data-conversation-id="${conversationId}"]`)
      .getByRole("link")
      .click();
    await expect(page).toHaveURL(
      new RegExp(`/${SITE_ID}/conversation/${conversationId}$`),
    );

    const panel = page.getByTestId("rail-strategy-panel");
    if (!(await panel.isVisible())) {
      await page.getByRole("button", { name: /^(Open|Close) Strategy$/ }).click();
    }
    await expect(panel).toBeVisible({ timeout: 20_000 });
    await expect(
      page.getByTestId(`compact-step-row-${EXPORTED_STEP.id}`),
    ).toContainText(EXPORTED_STEP.displayName);
    // The recorded step's own estimated size.
    await expect(
      page.getByTestId(`compact-step-row-${EXPORTED_STEP.id}`),
    ).toContainText("1,543");
  });
});
