/**
 * Two canvas edits on one combine strategy: the operator flip keeps its combine
 * node, the parameter edit keeps its leaf and the leaf's whole parameter set,
 * neither undoes the other, and the model reads the edited strategy.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { LAYOUTS, TRANSMEMBRANE, layoutOf } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readNodes, siteOrganism } from "../fixtures/site-reads";
import {
  buildOn,
  combineWith,
  expectCanvasSaved,
  expectCountAnswered,
  nodeById,
  nodeBySearch,
  openCanvas,
  paramNames,
  paramText,
} from "../fixtures/strategy-builds";

test.describe("Complex combine strategy edited on the canvas", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("an operator flip and a leaf edit both persist, and the model reads them", async ({
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
    const built = await readNodes(apiClient, id);
    const combineId = combineWith(built, "UNION").id ?? "";
    const leaf = nodeBySearch(built, TRANSMEMBRANE);
    const storedMinimum = paramText(leaf, "min_tm");
    const editedMinimum = String(Number(storedMinimum) + 1);

    await openCanvas(graphPage, siteId, id);
    await graphPage.changeOperator(combineId, "INTERSECT");
    await expectCanvasSaved(graphPage);
    await expect
      .poll(async () => nodeById(await readNodes(apiClient, id), combineId).operator, {
        timeout: 30_000,
      })
      .toBe("INTERSECT");

    await graphPage.clickNode(leaf.id ?? "");
    await expect(graphPage.editorSheet).toBeVisible({ timeout: 20_000 });
    const minimum = graphPage.editorSheet.locator('input[name="min_tm"]');
    await expect(minimum).toHaveValue(storedMinimum, { timeout: 15_000 });
    await expect(
      graphPage.editorSheet.getByText(/[1-9]\d* of \d+ selected/),
    ).toBeVisible({ timeout: 15_000 });
    await expect(graphPage.editorSheet.getByText(/^0 of \d+ selected$/)).toHaveCount(0);
    await minimum.fill(editedMinimum);
    await graphPage.saveEditor();
    await expectCanvasSaved(graphPage);

    await expect
      .poll(
        async () =>
          paramText(
            nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE),
            "min_tm",
          ),
        { timeout: 30_000 },
      )
      .toBe(editedMinimum);
    const edited = await readNodes(apiClient, id);
    expect(layoutOf(edited)).toEqual(LAYOUTS.intersect);
    expect(nodeById(edited, combineId).operator).toBe("INTERSECT");
    const editedLeaf = nodeBySearch(edited, TRANSMEMBRANE);
    expect(editedLeaf.id).toBe(leaf.id);
    expect(paramNames(editedLeaf)).toEqual(paramNames(leaf));

    await page.goto(`/${siteId}/conversation/${id}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await expectCountAnswered(chatPage, apiClient, id, siteId);
  });
});
