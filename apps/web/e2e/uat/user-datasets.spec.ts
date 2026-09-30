/**
 * UAT flow UD1: DESeq2 on the researcher's own counts upload, exported at the
 * cut the message states. The step runs the site's user-dataset search, and the
 * facts show both thresholds as stated. Every count is read from the site at
 * run time; only the model is mocked. The account holds `pathfinder-uat-deseq`
 * on each site (docs/knowledge/uat/sites-and-accounts.md).
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import type { ApiClient } from "../fixtures/api-client";
import { ownDatasets } from "../fixtures/eda-reads";
import { readNodes, siteCounts } from "../fixtures/site-reads";
import { nodeBySearch, paramText } from "../fixtures/strategy-builds";

const UPLOAD = "pathfinder-uat-deseq";
const DESEQ_USER_DATASET_SEARCH = "GenesByDESeqUserDataset";
const UD1_TEXT =
  `On my uploaded RNA-Seq dataset '${UPLOAD}', run DESeq2 of treated against ` +
  "control and keep the up-regulated genes with log2 fold change > 5 and " +
  "p-value < 1e-10.";
/** A comparison is one durable compute plus the turns around it. */
const COMPARISON_BUDGET_MS = 420_000;

/** The upload's study id, once the account's listing shows it installed. */
async function installedUpload(api: ApiClient, siteId: string): Promise<string> {
  const upload = (await ownDatasets(api, siteId)).find(
    (row) => row.name === UPLOAD && row.datasetId !== null,
  );
  expect(upload, `${UPLOAD} installed on ${siteId}`).toBeDefined();
  return upload?.datasetId ?? "";
}

test.describe("User-dataset flows", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 900_000 });

  test("UD1 - DESeq2 on an upload at a stated cut", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const datasetId = await installedUpload(apiClient, siteId);
    await chatPage.startOn(siteId);
    await chatPage.send(prompt("user-dataset-deseq", UD1_TEXT));
    const id = chatPage.lastStrategyId ?? "";

    const task = page
      .getByTestId("task-row")
      .filter({ hasText: "Run differential expression" });
    await expect(task).toBeVisible({ timeout: COMPARISON_BUDGET_MS });
    await expect(task.getByTestId("task-row-status")).not.toHaveText(
      /^(Queued|\d+%|Failed)$/,
      { timeout: COMPARISON_BUDGET_MS },
    );
    await expect(chatPage.sendButton).toBeVisible({ timeout: COMPARISON_BUDGET_MS });
    const facts = page.getByTestId("facts-step");
    await expect(facts).toHaveCount(1);

    const step = nodeBySearch(
      await readNodes(apiClient, id),
      DESEQ_USER_DATASET_SEARCH,
    );
    expect(paramText(step, "eda_dataset_id")).toBe(datasetId);

    const counts = await siteCounts(apiClient, id, siteId);
    await expect(page.getByTestId("facts-root-count")).toHaveAttribute(
      "data-count",
      String(counts.root),
    );
    await expect(facts.getByTestId("facts-step-count")).toHaveAttribute(
      "data-count",
      String(counts.root),
    );

    const params = page.getByTestId("facts-param");
    const effect = params.filter({ hasText: "log2(Fold Change)" });
    await expect(effect).toHaveAttribute("data-source", "stated");
    await expect(effect.getByTestId("facts-param-value")).toContainText("5");
    const significance = params.filter({ hasText: "Significance threshold" });
    await expect(significance).toHaveAttribute("data-source", "stated");
    await expect(significance.getByTestId("facts-param-value")).toContainText("1e-10");
    await expect(params.filter({ hasText: "Effect direction" })).toContainText(
      "upOnly",
    );
  });
});
