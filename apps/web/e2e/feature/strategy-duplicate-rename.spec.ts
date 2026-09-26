/**
 * Two step actions on the canvas: a rename in the step editor reaches the
 * stored step, and "Intersect with a copy" adds the copy and its combine while
 * the original step stays.
 */

import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { COMBINE_SEARCH_NAME } from "../fixtures/ast";
import { LAYOUTS, TRANSMEMBRANE } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readNodes, siteOrganism } from "../fixtures/site-reads";
import {
  buildOn,
  expectCanvasSaved,
  nodeById,
  nodeBySearch,
  openCanvas,
} from "../fixtures/strategy-builds";

const RENAMED = "Renamed transmembrane step";

async function intersectWithACopy(page: Page, stepId: string): Promise<void> {
  await page.getByTestId(`rf-node-${stepId}`).hover();
  await page.getByTestId(`rf-more-${stepId}`).click();
  await page.getByRole("menuitem", { name: "Intersect with a copy" }).click();
}

test.describe("Rename a step and intersect it with a copy", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("a renamed step keeps its name and its id when a copy is intersected with it", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt(
        "union",
        `Find ${siteOrganism(siteId)} genes that have a predicted signal peptide or 2 to 99 transmembrane domains.`,
      ),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.union);
    const leafId = nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE).id ?? "";

    await openCanvas(graphPage, siteId, id);
    await graphPage.expectNodeVisible(leafId);
    await graphPage.clickNode(leafId);
    await expect(graphPage.editorSheet).toBeVisible({ timeout: 20_000 });
    await graphPage.editorStepNameInput.fill(RENAMED);
    await graphPage.editorStepNameInput.press("Enter");
    await graphPage.saveEditor();
    await expectCanvasSaved(graphPage);
    await expect
      .poll(async () => nodeById(await readNodes(apiClient, id), leafId).displayName, {
        timeout: 30_000,
      })
      .toBe(RENAMED);

    await intersectWithACopy(page, leafId);
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 45_000 },
    );
    await expect
      .poll(async () => (await readNodes(apiClient, id)).length, { timeout: 30_000 })
      .toBe(LAYOUTS.union.steps + 2);
    const grown = await readNodes(apiClient, id);
    expect(
      grown
        .filter((node) => node.searchName === COMBINE_SEARCH_NAME)
        .map((node) => node.operator)
        .sort(),
    ).toEqual(["INTERSECT", "UNION"]);
    expect(nodeById(grown, leafId).displayName).toBe(RENAMED);
  });
});
