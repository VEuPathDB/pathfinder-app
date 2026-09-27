/**
 * An organism the request names is a value of each search, never a step of its
 * own: on vectorbase the mock FRAME binds the site organism alone beside the
 * signal peptide criterion, and the structure fold drops it. Every count is
 * read from the site at run time; only the model is mocked.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { LAYOUTS, SIGNAL_PEPTIDE } from "../fixtures/arc-layouts";
import { expectBuild, openTrace, traceRows } from "../fixtures/build-checks";
import { countPattern, readNodes, siteOrganism } from "../fixtures/site-reads";
import { buildOn, nodeBySearch, paramText } from "../fixtures/strategy-builds";

const SITE = "vectorbase";

test.describe("An organism named alone", { tag: "@named-site" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("The organism criterion leaves the tree", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    const organism = siteOrganism(SITE);
    const id = await buildOn(
      chatPage,
      SITE,
      prompt(
        "organism-universe",
        `Find ${organism} genes whose proteins have a predicted signal peptide.`,
      ),
    );

    const counts = await expectBuild(page, apiClient, id, SITE, LAYOUTS.single);
    const leaf = nodeBySearch(await readNodes(apiClient, id), SIGNAL_PEPTIDE);
    expect(paramText(leaf, "organism")).toContain(organism);

    const reply = chatPage.assistantReply(countPattern(counts.root));
    await expect(reply).not.toHaveCount(0);
    await openTrace(reply);
    await expect(
      traceRows(reply, "Arrange the steps").getByTestId("trace-row-summary"),
    ).toContainText(["Structure set: 1 search; dropped organism_genes"]);
  });
});
