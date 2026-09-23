/**
 * Journey 3: a completed compute exports a step the strategy rail lists.
 *
 * The export PATCH is answered in the browser, so the step exists only in the
 * query cache the export wrote. The walk back to the thread is therefore a
 * client-side navigation; a reload would refetch the untouched server strategy.
 */

import type { BrowserContext } from "@playwright/test";

import { test, expect, BASE_URL } from "../fixtures/test";
import { CSRF_HEADERS } from "../fixtures/api-client";
import {
  analysisState,
  COMPUTE_JOB,
  DATASET_ID,
  edaJson,
  EXPORTED_STEP,
  exportedStrategy,
  routeEdaReads,
  SITE_ID,
  TEMPERATURE_VAR,
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
  test("a completed compute exports a step the strategy rail lists", async ({
    page,
    context,
  }) => {
    const conversationId = await openConversation(context);
    await routeEdaReads(page);

    const actions: string[] = [];
    await page.route(`**/api/v1/conversations/${conversationId}/eda`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill(edaJson({ analysis: null, descriptor: null }));
        return;
      }
      const body = route.request().postDataJSON() as { action: string };
      actions.push(body.action);
      if (body.action === "run-compute") {
        await route.fulfill(
          edaJson({
            analysis: analysisState({ revision: 1, numComputations: 1 }),
            job: COMPUTE_JOB,
            step: null,
          }),
        );
        return;
      }
      if (body.action === "export-step") {
        await route.fulfill(
          edaJson({
            analysis: analysisState({ revision: 2, numComputations: 1 }),
            job: null,
            step: exportedStrategy(conversationId),
          }),
        );
        return;
      }
      await route.fulfill(
        edaJson({ analysis: analysisState(), job: null, step: null }),
      );
    });

    await page.goto(`/${SITE_ID}/conversation/${conversationId}/eda`);
    await page.getByTestId("eda-study-search").fill("heat shock");
    await page.getByTestId(`eda-study-row-${DATASET_ID}`).click();
    await expect(page.getByTestId("eda-compute-cell")).toBeVisible({ timeout: 20_000 });

    await page.getByLabel("Comparator variable").selectOption(TEMPERATURE_VAR);
    await page
      .getByRole("group", { name: "Reference group (A)" })
      .getByRole("checkbox", { name: "normal" })
      .click();
    await page
      .getByRole("group", { name: "Comparison group (B)" })
      .getByRole("checkbox", { name: "febrile" })
      .click();
    await page.getByRole("button", { name: "Run compute" }).click();
    await expect(page.getByTestId("eda-compute-complete")).toBeVisible({
      timeout: 20_000,
    });

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
    expect(actions).toEqual(["bind", "run-compute", "export-step"]);

    // Client-side navigation back to the thread keeps the query cache the
    // export wrote the strategy into.
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
