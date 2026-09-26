/**
 * A two-search build as the canvas draws it: both searches feed the one
 * combine, and every stored node is on the canvas.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { COMBINE_SEARCH_NAME } from "../fixtures/ast";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readNodes, siteOrganism } from "../fixtures/site-reads";
import { buildOn, combineWith, openCanvas } from "../fixtures/strategy-builds";

test.describe("Execution phase", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("a UNION build feeds both searches into its combine and draws every node", async ({
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

    const nodes = await readNodes(apiClient, id);
    const combine = combineWith(nodes, "UNION");
    const leafIds = nodes
      .filter((node) => node.searchName !== COMBINE_SEARCH_NAME)
      .map((node) => node.id)
      .sort();
    expect([combine.primaryInput?.id, combine.secondaryInput?.id].sort()).toEqual(
      leafIds,
    );

    await openCanvas(graphPage, siteId, id);
    await graphPage.expectNodeCount(LAYOUTS.union.steps);
    for (const node of nodes) await graphPage.expectNodeVisible(node.id ?? "");
    await expect(graphPage.strategyPageStepCount).toHaveText(
      `${LAYOUTS.union.steps} steps`,
    );
  });
});
