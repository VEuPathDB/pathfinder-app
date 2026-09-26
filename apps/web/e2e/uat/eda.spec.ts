/**
 * UAT flows E1 to E4 and E8: picking a study, the comparison the assistant
 * runs, the read-only tab and its export. The study, its groups and every count
 * are read from the api and the site at run time; only the model is mocked.
 */

import type { Locator, Page } from "@playwright/test";
import { siteShortName, type SiteResponse } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import type { ApiClient } from "../fixtures/api-client";
import { expectBuild, expectEvidence, traceRows } from "../fixtures/build-checks";
import {
  EDA_VIZ_SEARCH,
  comparisonSentence,
  computeOf,
  cutSentence,
  entityCaption,
  entityLine,
  exportedStepName,
  groupsLine,
  openAnalysis,
  browseStudies,
  ownStudy,
  railStudyLine,
  readAnalysis,
  readVolcano,
  retainedClause,
  selectionSentence,
} from "../fixtures/eda-reads";
import { layoutOf } from "../fixtures/arc-layouts";
import {
  printed,
  readConversation,
  siteCounts,
  storedNodes,
} from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";
import type { GraphPage } from "../pages/graph.page";

/** A comparison is one durable compute plus the turns around it. */
const COMPARISON_BUDGET_MS = 420_000;
const READOUT_LIMIT = 50;
/**
 * The mock searches studies with the message's own words, and the stack ranks
 * studies by name, so the message is the title of a study the site publishes.
 */
async function compareText(api: ApiClient, siteId: string): Promise<string> {
  return (await ownStudy(api, siteId)).displayName;
}
const COMPARISON_TOOLS = [
  "Find studies",
  "Open study",
  "Filter samples",
  "Preview samples",
  "Run differential expression",
];

function conversationOf(chatPage: ChatPage): string {
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  return id;
}

/** Send the comparison and wait until its figure is drawn and the task settled. */
async function runComparison(
  chatPage: ChatPage,
  page: Page,
  siteId: string,
  message: string,
): Promise<string> {
  await chatPage.startOn(siteId);
  await chatPage.send(message);
  await expect(page.getByTestId("data-eda-viz")).toBeVisible({
    timeout: COMPARISON_BUDGET_MS,
  });
  const task = page
    .getByTestId("task-row")
    .filter({ hasText: "Run differential expression" });
  await expect(task.getByTestId("task-row-status")).not.toHaveText(
    /^(Queued|\d+%|Failed)$/,
    { timeout: COMPARISON_BUDGET_MS },
  );
  await expect(chatPage.sendButton).toBeVisible({ timeout: COMPARISON_BUDGET_MS });
  await expect(chatPage.messageInput).toBeEditable();
  return conversationOf(chatPage);
}

/** The thread's study card, its figure and the step all state what the api reads. */
async function expectComparisonInThread(
  page: Page,
  api: ApiClient,
  siteId: string,
  conversationId: string,
) {
  const analysis = await openAnalysis(api, conversationId);
  const compute = computeOf(analysis);
  const viz = await readVolcano(api, siteId, conversationId);
  expect(viz.comparison.groupA).toEqual(compute.groupA);
  expect(viz.comparison.groupB).toEqual(compute.groupB);

  const card = page.getByTestId("data-eda-analysis-state");
  await expect(card).toHaveCount(1);
  await expect(card.locator("figcaption")).toContainText(analysis.studyDisplayName);
  await expect(card.getByTestId("figure-caption")).toHaveText(entityCaption(analysis));
  for (const [index, summary] of analysis.filterSummaries.entries()) {
    await expect(card.getByTestId(`data-eda-filter-chip-${String(index)}`)).toHaveText(
      summary,
    );
  }
  await expect(
    card.getByRole("link", { name: `Open in ${siteShortName(siteId)}` }),
  ).toHaveAttribute("href", analysis.analysisUrl ?? "");
  await expect(
    card.getByRole("button", { name: "Open study", exact: true }),
  ).toBeVisible();

  const figure = page.getByTestId("data-eda-viz");
  await expect(figure.locator("figcaption")).toContainText(viz.effectSizeLabel);
  await expect(figure.getByTestId("figure-caption")).toContainText(
    `${analysis.studyDisplayName} - ${retainedClause(viz)}`,
  );
  await expect(figure.getByTestId("eda-viz-comparison")).toHaveText(
    groupsLine(viz.comparison),
  );
  await expect(figure.locator("summary")).toContainText(
    `Gene ids (${printed(viz.retainedPoints)})`,
  );
  await expect(figure.getByRole("button", { name: "Copy gene ids" })).toHaveCount(1);
  return { analysis, viz };
}

/** Open the Studies rail and read the analysis the conversation holds. */
async function expectStudiesRail(page: Page, api: ApiClient, conversationId: string) {
  const analysis = await openAnalysis(api, conversationId);
  await showStudies(page);
  const panel = page.getByTestId("rail-eda-panel");
  await expect(panel).toContainText(analysis.studyDisplayName);
  await expect(panel).toContainText(railStudyLine(analysis));
}

/** Leave the tab for the thread and wait for the composer. */
/** Bring the rail's Studies panel on screen; it stays open once a reader opened it. */
async function showStudies(page: Page) {
  // The rail mounts with the conversation, so wait for the conversation first.
  await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });
  const open = page
    .getByLabel("Right rail")
    .getByRole("button", { name: "Open Studies", exact: true });
  if ((await open.count()) > 0) await open.click();
  await expect(page.getByTestId("rail-eda-panel")).toBeVisible();
}

async function backToThread(page: Page, chatPage: ChatPage) {
  await page.getByRole("link", { name: "Back to conversation" }).click();
  await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
}

/** The rail lists the one exported step, at the count the site answers. */
async function expectOneExportedStep(
  graphPage: GraphPage,
  api: ApiClient,
  conversationId: string,
  siteId: string,
  stepName: string,
): Promise<number> {
  const counts = await siteCounts(api, conversationId, siteId);
  await graphPage.openRailStrategyPanel();
  await expect(graphPage.railFooter).toHaveText("1 step");
  await expect(graphPage.railStepRows).toHaveCount(1);
  await expect(graphPage.railStepRows).toContainText(stepName);
  await expect(graphPage.railPanel).toContainText(printed(counts.root));
  return counts.root;
}

/** The tab's header, subset and comparison cells for an analysis with no comparison. */
async function expectFreshTab(
  tab: Locator,
  siteId: string,
  conversationId: string,
  api: ApiClient,
) {
  const analysis = await openAnalysis(api, conversationId);
  await expect(tab.getByTestId("eda-workbench-title")).toHaveText(
    analysis.studyDisplayName,
  );
  await expect(
    tab.getByRole("link", { name: `Open in ${siteShortName(siteId)}` }),
  ).toHaveAttribute("href", analysis.analysisUrl ?? "");
  await expect(tab.getByRole("button", { name: "Change study" })).toBeEnabled();
  await expect(tab.getByRole("button", { name: "Export as step" })).toBeDisabled();
  await expect(tab.getByTestId("eda-subset-no-filters")).toHaveText(
    "No filters: the subset is the whole study.",
  );
  for (const entity of analysis.entityCounts) {
    expect(entity.count).toBe(entity.unfilteredCount);
    await expect(tab.getByTestId(`eda-entity-count-${entity.entityId}`)).toHaveText(
      entityLine(entity),
    );
  }
  await expect(tab.getByTestId("eda-comparison-none")).toHaveText(
    "No comparison has run on this analysis. Ask for one in the conversation.",
  );
  await expect(tab.locator("input, select, textarea")).toHaveCount(0);
  return analysis;
}

test.describe("Studies", () => {
  test("E1 - Pick a study in the tab", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    // The site's study listing and each tab render read the live site.
    test.setTimeout(300_000);
    const study = await ownStudy(apiClient, siteId);
    await chatPage.startOn(siteId);
    await chatPage.sendTurn("Which studies can I explore here?", /\[mock\]/);
    const id = conversationOf(chatPage);

    await showStudies(page);
    const rail = page.getByTestId("rail-eda-panel");
    await expect(rail).toContainText("No study is open");
    await expect(rail).toContainText(
      "Ask the assistant to explore a study, and the subset and its plots appear here.",
    );

    await page.goto(`/${siteId}/conversation/${id}/eda`);
    const tab = page.getByTestId("eda-workbench");
    const header = tab.getByTestId("eda-workbench-header");
    await expect(header).toContainText("No study selected", { timeout: 60_000 });
    await expect(
      header.getByRole("link", { name: "Back to conversation" }),
    ).toHaveAttribute("href", `/${siteId}/conversation/${id}`);
    const datasets = tab.getByTestId("eda-your-datasets");
    await expect(
      datasets.getByRole("heading", { name: "Your datasets" }),
    ).toBeVisible();
    await expect(
      datasets.getByRole("link", { name: "Upload on VEuPathDB" }),
    ).toBeVisible({
      timeout: 60_000,
    });
    const search = tab.getByPlaceholder("Search studies...");
    await expect(search).toBeVisible();

    await search.fill("h");
    await expect(
      tab.getByText("Type at least 2 characters to search studies.", { exact: true }),
    ).toBeVisible();

    await search.fill(study.displayName);
    const row = tab.getByTestId(`eda-study-row-${study.datasetId}`);
    await expect(row).toContainText(study.displayName, { timeout: 60_000 });
    await expect(row).toContainText(study.datasetId);
    await expect(tab.getByTestId(`eda-study-sites-${study.datasetId}`)).toHaveText(
      study.sites.join(", "),
    );

    await row.click();
    await expect(tab.getByTestId("eda-workbench-title")).toBeVisible({
      timeout: 60_000,
    });
    const analysis = await expectFreshTab(tab, siteId, id, apiClient);
    expect(analysis.datasetId).toBe(study.datasetId);

    await tab.getByRole("button", { name: "Change study" }).click();
    await expect(tab.getByTestId("eda-study-picker")).toBeVisible({ timeout: 30_000 });
    expect(await readAnalysis(apiClient, id)).toBeNull();
    await backToThread(page, chatPage);
    await showStudies(page);
    await expect(page.getByTestId("rail-eda-panel")).toContainText("No study is open");
  });

  test.describe("The assistant's comparison", { tag: "@turn" }, () => {
    test.describe.configure({ timeout: 600_000 });

    test("E2 - The assistant runs a comparison", async ({
      chatPage,
      apiClient,
      page,
      siteId,
    }) => {
      const id = await runComparison(
        chatPage,
        page,
        siteId,
        prompt("eda-compare", await compareText(apiClient, siteId)),
      );
      for (const label of [...COMPARISON_TOOLS, "Add study step"]) {
        await expect(traceRows(chatPage.assistantMessages, label)).not.toHaveCount(0);
      }
      const { viz } = await expectComparisonInThread(page, apiClient, siteId, id);

      await expect
        .poll(async () => layoutOf(await storedNodes(apiClient, id)).searches, {
          timeout: COMPARISON_BUDGET_MS,
        })
        .toEqual([EDA_VIZ_SEARCH]);
      const counts = await expectBuild(page, apiClient, id, siteId, {
        steps: 1,
        searches: [EDA_VIZ_SEARCH],
        operators: [],
      });
      expect(counts.root).toBe(viz.retainedPoints);
      const [step] = (await readConversation(apiClient, id)).steps ?? [];
      expect(step?.displayName).toBe(exportedStepName(viz));
      await expect(page.getByTestId("rail-strategy-panel")).toContainText(
        exportedStepName(viz),
      );
      await expectEvidence(page, "Supported", counts.root);

      await expectStudiesRail(page, apiClient, id);
    });

    test("E3 - The read-only tab after a comparison", async ({
      chatPage,
      apiClient,
      page,
      siteId,
    }) => {
      const id = await runComparison(
        chatPage,
        page,
        siteId,
        prompt("eda-compare", await compareText(apiClient, siteId)),
      );
      const { analysis, viz } = await expectComparisonInThread(
        page,
        apiClient,
        siteId,
        id,
      );

      await page
        .getByTestId("data-eda-analysis-state")
        .getByRole("button", { name: "Open study", exact: true })
        .click();
      await expect(page).toHaveURL(new RegExp(`/${siteId}/conversation/${id}/eda$`), {
        timeout: 60_000,
      });
      const tab = page.getByTestId("eda-workbench");
      await expect(tab.getByTestId("eda-workbench-title")).toHaveText(
        analysis.studyDisplayName,
        { timeout: 60_000 },
      );
      for (const [index, summary] of analysis.filterSummaries.entries()) {
        await expect(tab.getByTestId(`eda-filter-chip-${String(index)}`)).toHaveText(
          summary,
        );
      }
      for (const entity of analysis.entityCounts) {
        await expect(tab.getByTestId(`eda-entity-count-${entity.entityId}`)).toHaveText(
          entityLine(entity),
        );
      }
      await expect(tab.getByTestId("eda-comparison-sentence")).toHaveText(
        comparisonSentence(computeOf(analysis)),
      );
      await expect(tab.getByTestId("eda-volcano-cut")).toHaveText(cutSentence(viz), {
        timeout: 60_000,
      });
      await expect(tab.getByTestId("eda-volcano-selection")).toHaveText(
        selectionSentence(viz),
      );
      for (const name of ["Gene", "Effect", "p"]) {
        await expect(tab.getByRole("columnheader", { name, exact: true })).toHaveCount(
          1,
        );
      }
      const listed = tab.locator('[data-testid^="eda-volcano-gene-"]');
      await expect(listed).toHaveCount(Math.min(viz.retainedPoints, READOUT_LIMIT));
      if (viz.retainedPoints > READOUT_LIMIT) {
        await expect(tab.getByTestId("eda-volcano-readout-cap")).toHaveText(
          `The first ${String(READOUT_LIMIT)} of ${String(viz.retainedPoints)} selected genes are listed.`,
        );
      }
      await expect(tab.locator("input, select, textarea")).toHaveCount(0);
    });

    test("E4 - Export as a step from the tab", async ({
      chatPage,
      graphPage,
      apiClient,
      page,
      siteId,
    }) => {
      const id = await runComparison(
        chatPage,
        page,
        siteId,
        prompt("eda-compare-no-step", await compareText(apiClient, siteId)),
      );
      const { viz } = await expectComparisonInThread(page, apiClient, siteId, id);
      await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
      expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);

      await page.goto(`/${siteId}/conversation/${id}/eda`);
      const tab = page.getByTestId("eda-workbench");
      const exportButton = tab.getByRole("button", { name: "Export as step" });
      await expect(exportButton).toBeEnabled({ timeout: 60_000 });
      await exportButton.click();
      const began = tab.getByTestId("eda-export-began-strategy");
      await expect(began).toContainText("This step is now the strategy's first step.", {
        timeout: 120_000,
      });
      await expect(
        began.getByRole("link", { name: "Open the strategy canvas" }),
      ).toHaveAttribute("href", `/${siteId}/conversation/${id}/strategy`);
      await expect(tab.getByTestId("eda-export-step-name")).toHaveText(
        `Exported: ${exportedStepName(viz)}`,
      );

      await backToThread(page, chatPage);
      const root = await expectOneExportedStep(
        graphPage,
        apiClient,
        id,
        siteId,
        exportedStepName(viz),
      );
      expect(root).toBe(viz.retainedPoints);
    });

    test("E8 - A study another site publishes", async ({
      chatPage,
      graphPage,
      apiClient,
      page,
      siteId,
    }) => {
      // The mock searches studies with the message's own words, ranked by name.
      const elsewhere = (await browseStudies(apiClient, siteId)).find(
        (study) => study.notHere !== null,
      );
      const question = elsewhere?.displayName ?? "";
      expect(question).not.toBe("");
      await chatPage.startOn(siteId);
      await chatPage.sendAndSettle(prompt("eda-other-site", question));
      const id = conversationOf(chatPage);

      const sites = await apiClient.get("/api/v1/sites");
      expect(sites.status()).toBe(200);
      const others = ((await sites.json()) as SiteResponse[])
        .filter((site) => site.id !== siteId)
        .map((site) => site.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
      await expect(
        chatPage.assistantReply(new RegExp(`\\b(${others.join("|")})\\b`)),
      ).not.toHaveCount(0);

      await expect(page.getByTestId("data-eda-analysis-state")).toHaveCount(0);
      await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
      expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
      expect(await readAnalysis(apiClient, id)).toBeNull();
      await graphPage.showRailStrategy();
      await expect(graphPage.railEmptyHeading).toBeVisible();
    });
  });
});
