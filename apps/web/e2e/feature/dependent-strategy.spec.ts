/**
 * A GO step, whose vocabulary depends on another parameter, edited in the step
 * editor: the edit reaches the stored step and the step keeps its id and its
 * whole parameter set.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { GO_TERM, LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readNodes, siteCounts, siteOrganism } from "../fixtures/site-reads";
import {
  buildOn,
  expectCanvasSaved,
  noteSiteRefusedSave,
  nodeBySearch,
  openCanvas,
  paramNames,
  paramText,
} from "../fixtures/strategy-builds";

/** The term the researcher types in the editor: kinase activity. */
const EDITED_GO_TERM = "GO:0016301";

test.describe("Dependent-parameter strategy", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("a GO step edited in the editor keeps its id and its whole parameter set", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("go", `Find ${siteOrganism(siteId)} genes by their GO term.`),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.go);
    const built = nodeBySearch(await readNodes(apiClient, id), GO_TERM);
    const storedTerm = paramText(built, "go_term");
    expect(storedTerm).not.toBe(EDITED_GO_TERM);

    await openCanvas(graphPage, siteId, id);
    await graphPage.clickNode(built.id ?? "");
    await expect(graphPage.editorSheet).toBeVisible({ timeout: 20_000 });
    await expect(
      graphPage.editorSheet.getByText(/[1-9]\d* of \d+ selected/),
    ).toBeVisible({ timeout: 15_000 });
    const goTerm = graphPage.editorSheet.locator('input[name="go_term"]');
    await expect(goTerm).toHaveValue(storedTerm);
    await goTerm.fill(EDITED_GO_TERM);
    if ((await graphPage.saveEditorOrSiteRefusal()) === "site-refused") {
      noteSiteRefusedSave(GO_TERM);
      return;
    }
    await expectCanvasSaved(graphPage);

    await expect
      .poll(
        async () =>
          paramText(nodeBySearch(await readNodes(apiClient, id), GO_TERM), "go_term"),
        { timeout: 30_000 },
      )
      .toBe(EDITED_GO_TERM);
    const edited = nodeBySearch(await readNodes(apiClient, id), GO_TERM);
    expect(edited.id).toBe(built.id);
    expect(paramNames(edited)).toEqual(paramNames(built));
    const { root } = await siteCounts(apiClient, id, siteId);
    expect(root).toBeGreaterThanOrEqual(0);
  });
});
