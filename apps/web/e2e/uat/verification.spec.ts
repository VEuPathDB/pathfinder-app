/**
 * UAT flows V1 to V5 and V7: the evidence card a check leaves, control tests on
 * a step, the parameter sweep, a strategy built from controls, and a variant
 * comparison. Counts, ids and control sets are read from the site at run time.
 */

import type { Locator, Page } from "@playwright/test";
import { siteShortName } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { type ApiClient, fetchConversationMessages } from "../fixtures/api-client";
import { LAYOUTS, TRANSMEMBRANE, layoutOf } from "../fixtures/arc-layouts";
import { expectBuild, openTrace, traceRows } from "../fixtures/build-checks";
import {
  type SiteCounts,
  countPattern,
  printed,
  readConversation,
  readNodes,
  siteControlSets,
  siteGeneIdPrefix,
  siteOrganism,
  siteRow,
} from "../fixtures/site-reads";
import { buildOn, nodeBySearch, paramText } from "../fixtures/strategy-builds";
import type { ChatPage } from "../pages/chat.page";

/** Wall clock a durable task on the live site needs before its figure lands. */
const TASK_BUDGET_MS = 600_000;

const S1_TEXT = (organism: string) =>
  `Find ${organism} genes whose proteins have a predicted signal peptide.`;
const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;

/** The seed control set a message pastes: the signal peptide one, else the first. */
function pastedControls(siteId: string) {
  const sets = siteControlSets(siteId);
  const [first] = sets;
  const chosen = sets.find((set) => /signal peptide/i.test(set.name)) ?? first;
  if (chosen === undefined) throw new Error(`the ${siteId} seeds carry no control set`);
  return chosen;
}

/** The two control lines a researcher pastes under a request. */
function controlLines(siteId: string): string {
  const set = pastedControls(siteId);
  return [
    `Positive controls: ${set.positive_ids.join(" ")}`,
    `Negative controls: ${set.negative_ids.join(" ")}`,
  ].join("\n");
}

/** Whether `positives`/`negatives` are the sizes of one of the site's seed control sets. */
function isSeedSetSize(siteId: string, positives: number, negatives: number): boolean {
  return siteControlSets(siteId).some(
    (set) =>
      set.positive_ids.length === positives && set.negative_ids.length === negatives,
  );
}

/** A printed count as a number. */
function numberOf(text: string): number {
  return Number(text.replace(/,/g, ""));
}

/** The body cells of one table, row by row. */
async function bodyCells(table: Locator): Promise<string[][]> {
  return table
    .locator("tbody tr")
    .evaluateAll((rows) =>
      rows.map((row) =>
        Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent.trim()),
      ),
    );
}

/** The row whose first cell is `label`. */
function rowOf(rows: readonly string[][], label: string): string[] {
  const row = rows.find((cells) => cells[0] === label);
  if (row === undefined) throw new Error(`no ${label} row`);
  return row;
}

/** Bring a rail panel on screen and return its scroller. */
async function openRail(page: Page, label: string): Promise<Locator> {
  const open = page.getByRole("button", { name: `Open ${label}`, exact: true });
  if ((await open.count()) > 0) await open.click();
  const region = page.getByRole("region", { name: `${label} detail`, exact: true });
  await expect(region).toBeVisible();
  return region;
}

/** Open the rail's Progress panel on its Checking tab. */
async function openChecking(page: Page): Promise<Locator> {
  await openRail(page, "Progress");
  const panel = page.getByTestId("ledger-panel");
  await panel.getByRole("button", { name: /^Checking/ }).click();
  return panel;
}

/** Every assistant reply of the conversation as the event log holds it, joined. */
async function replyText(api: ApiClient, conversationId: string): Promise<string> {
  const messages = await fetchConversationMessages(api, conversationId);
  return messages
    .filter((message) => message.role === "assistant")
    .map((message) => message.content)
    .join("\n");
}

/** The step table rows equal the site: each row's two counts agree with each other and with a step. */
async function expectStepTable(card: Locator, counts: SiteCounts) {
  const steps = card.getByTestId("evidence-steps");
  await expect(steps.getByRole("columnheader")).toHaveText([
    "Step",
    "Recorded at the build",
    "On the site at the check",
  ]);
  await expect(steps.getByTestId("evidence-step-changed")).toHaveCount(0);
  const rows = await bodyCells(steps);
  for (const row of rows) expect(row[1]).toBe(row[2]);
  const site = Object.values(counts.byStep)
    .filter((count): count is number => count !== null)
    .map(printed)
    .sort();
  expect(rows.map((row) => row[2] ?? "").sort()).toEqual(site);
}

/** Send the separation arc, approve its run and wait for the offer card. */
async function runSeparation(chatPage: ChatPage, page: Page, siteId: string) {
  await chatPage.sendAndSettle(
    prompt(
      "separation",
      `Find me a strategy that separates these controls, in exact mode.\n${controlLines(siteId)}`,
    ),
  );
  const approval = page.getByTestId("approval-card");
  await expect(approval.getByTestId("approval-card-title")).toHaveText(
    "Run the separation? It measures candidate searches against your controls on the site and takes about five minutes.",
    { timeout: 60_000 },
  );
  await approval.getByTestId("tool-approval-approve").click();
  await expect(page.getByTestId("tool-approval-decision")).toContainText("Approved");
  await expect(
    page.getByTestId("task-row").filter({ hasText: "Separate the controls" }),
  ).toHaveCount(1, { timeout: 120_000 });

  const result = page.getByTestId("data-separation-result");
  await expect(result).toBeVisible({ timeout: TASK_BUDGET_MS });
  const card = page.getByTestId("separation-card");
  await expect(card.getByTestId("separation-question")).toHaveText(
    /^Build the (separating strategy|closest strategy found): .+ in [\d,]+ genes\?$/,
    { timeout: 240_000 },
  );
  await expect(
    card.getByPlaceholder("Why not? (optional, sent with a no)"),
  ).toBeVisible();
  await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });
  return { result, card };
}

test.describe("Verification flows", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("V1 - The evidence card of a build", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    const card = page.getByTestId("data-evidence-card");
    await expect(card).toHaveCount(1, { timeout: 60_000 });

    await expect(card.getByTestId("figure-caption")).toHaveText(
      new RegExp(
        `^(\\d+) of \\1 requirements? met, (\\d+) of \\2 sampled genes? fits?, ${LAYOUTS.intersect.steps} steps counted on the site\\.$`,
      ),
    );
    await expect(card.getByTestId("evidence-verdict")).toHaveText("Supported");
    await expectStepTable(card, counts);

    const requirements = card.getByTestId("evidence-requirements");
    await expect(requirements.getByRole("columnheader")).toHaveText([
      "Requirement",
      "Answered by",
      "How",
      "Status",
    ]);
    const statuses = requirements.getByTestId("evidence-requirement-status");
    await expect(statuses).not.toHaveCount(0);
    for (const status of await statuses.allTextContents()) expect(status).toBe("Met");
    for (const row of await bodyCells(requirements))
      expect(row[0]).toContain("Message 1");

    const sampled = card.getByTestId("evidence-sampled-genes");
    await expect(sampled.getByRole("columnheader")).toHaveText([
      "Gene",
      "Product",
      "Fits",
      "Why",
    ]);
    const genes = await bodyCells(sampled);
    expect(genes.length).toBeGreaterThan(0);
    for (const gene of genes) {
      expect(gene[0] ?? "").toMatch(new RegExp(`^${siteGeneIdPrefix(siteId)}`));
      expect(gene[3] ?? "").not.toBe("");
    }

    const site = await siteRow(apiClient, siteId);
    const web = site.baseUrl
      .replace(/\/service$/, "")
      .replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const link = card.getByTestId("evidence-strategy-link");
    await expect(link).toHaveText(`Open in ${siteShortName(siteId)}`);
    await expect(link).toHaveAttribute(
      "href",
      new RegExp(`^${web}/app/workspace/strategies/\\d+/\\d+$`),
    );

    const rail = await openChecking(page);
    await expect(rail.getByTestId("evidence-verdict")).toHaveText("Supported");
    await expect(
      rail.getByText("complete", { exact: true }).locator(".."),
    ).toContainText("yes");
    await expect(
      rail.getByText("successful", { exact: true }).locator(".."),
    ).toContainText("yes");
    await expect(rail.getByTestId("evidence-superseded")).toHaveCount(0);

    const tm = paramText(
      nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE),
      "min_tm",
    );
    await chatPage.sendAndSettle(
      prompt("edit-param", "Change the transmembrane range to 1 to 99."),
    );
    await expect
      .poll(async () =>
        paramText(
          nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE),
          "min_tm",
        ),
      )
      .not.toBe(tm);
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    // The edit runs its own check, so the rail holds that newer card and the
    // older answer in the conversation carries the mark.
    const current = await openChecking(page);
    await expect(current.getByTestId("evidence-superseded")).toHaveCount(0);
    await expect(page.getByTestId("superseded-badge")).toContainText([
      "strategy changed since this answer",
    ]);
  });

  test("V2 - Control tests on a step", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await chatPage.sendAndSettle(
      prompt(
        "controls-test",
        `Test this strategy against my controls.\n${controlLines(siteId)}`,
      ),
    );
    await expect(
      page.getByTestId("task-row").filter({ hasText: "Run control tests" }),
    ).toHaveCount(1, { timeout: 120_000 });
    const figure = page.getByTestId("data-control-test-results");
    await expect(figure).toHaveCount(1, { timeout: TASK_BUDGET_MS });
    await expect(figure.getByTestId("figure-caption")).toHaveText(
      new RegExp(
        `^Table \\d+\\. Control tests on .+: target ${printed(counts.root)} records, `,
      ),
    );

    const card = page
      .getByTestId("data-evidence-card")
      .filter({ has: page.getByTestId("evidence-controls") });
    await expect(card).toHaveCount(1, { timeout: TASK_BUDGET_MS });
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });
    await expect(card.getByTestId("evidence-controls")).toHaveCount(1);
    const cardRows = await bodyCells(card.getByTestId("evidence-controls"));
    const positive = rowOf(cardRows, "Positive");
    const negative = rowOf(cardRows, "Negative");
    const positives = numberOf(positive[1] ?? "");
    const negatives = numberOf(negative[1] ?? "");
    expect(isSeedSetSize(siteId, positives, negatives)).toBe(true);
    expect(numberOf(positive[2] ?? "") + numberOf(positive[3] ?? "")).toBe(positives);
    expect(numberOf(negative[2] ?? "") + numberOf(negative[3] ?? "")).toBe(negatives);

    const figureRows = await bodyCells(figure);
    expect(rowOf(figureRows, "Positive")[2]).toBe(positive[2]);
    expect(rowOf(figureRows, "Negative")[2]).toBe(negative[2]);
    const reply = await replyText(apiClient, id);
    expect(reply).toMatch(countPattern(numberOf(positive[2] ?? "")));
    expect(reply).toMatch(countPattern(numberOf(negative[2] ?? "")));

    const tasks = await openRail(page, "Tasks");
    await expect(
      tasks.getByRole("listitem").filter({ hasText: "Run control tests" }),
    ).toContainText("Complete", { timeout: 60_000 });
  });

  test("V3 - Parameter sweep with its approval", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    test.setTimeout(900_000);
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await chatPage.sendAndSettle(
      prompt(
        "sweep",
        `Optimize the SignalP version of the signal peptide search to recover as many of my positive controls as possible while returning as few of my negative controls as possible.\n${controlLines(siteId)}`,
      ),
    );
    const approval = page.getByTestId("approval-card");
    await expect(approval.getByTestId("approval-card-title")).toHaveText(
      "Optimize parameters needs your approval before it runs.",
      { timeout: 60_000 },
    );
    await approval.getByTestId("tool-approval-approve").click();
    await expect(page.getByTestId("tool-approval-decision")).toContainText("Approved");
    await expect(
      page.getByTestId("task-row").filter({ hasText: "Optimize parameters" }),
    ).toHaveCount(1, { timeout: 120_000 });
    const tasks = await openRail(page, "Tasks");
    await expect(
      tasks.getByRole("listitem").filter({ hasText: "Optimize parameters" }),
    ).toHaveCount(1, { timeout: 60_000 });

    const figure = page.getByTestId("data-scored-comparison");
    await expect(figure).toHaveCount(1, { timeout: 780_000 });
    await expect(figure).toContainText("Scored variants");
    await expect(figure.getByTestId("figure-caption")).toHaveText(/^Table \d+\. /);
    await expect(figure.getByRole("columnheader")).toHaveText([
      "Variant",
      "MCC",
      "F1",
      "Precision",
      "Sensitivity",
      "Balanced accuracy",
    ]);
    expect((await bodyCells(figure)).length).toBeGreaterThan(1);
  });

  test("V4 - Controls in, strategy out", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    test.setTimeout(900_000);
    await chatPage.startOn(siteId);
    const id = chatPage.lastStrategyId ?? "";
    const { result, card } = await runSeparation(chatPage, page, siteId);

    for (const [cell, label] of [
      ["recovered", "Positives returned"],
      ["missed", "Positives missed"],
      ["admitted", "Negatives admitted"],
      ["excluded", "Negatives excluded"],
    ] as const) {
      await expect(result.getByTestId(`separation-cell-${cell}`)).toContainText(label);
    }
    const count = async (cell: string) =>
      numberOf(
        (await result
          .getByTestId(`separation-cell-${cell}`)
          .getByTestId("separation-count")
          .textContent()) ?? "",
      );
    const recovered = await count("recovered");
    const admitted = await count("admitted");
    const positives = recovered + (await count("missed"));
    const negatives = admitted + (await count("excluded"));
    expect(isSeedSetSize(siteId, positives, negatives)).toBe(true);

    const criteria = result.getByTestId("separation-criteria");
    await expect(criteria.getByRole("columnheader")).toHaveText([
      "Search",
      "Its own step",
      "Ablation",
    ]);
    for (const row of await bodyCells(criteria)) {
      expect(row[2] ?? "").toMatch(
        /^without it: ([+-]\d+|0) positives, ([+-]\d+|0) negatives$/,
      );
    }
    await expect(result.getByTestId("separation-informative")).toHaveText(
      /^\d+ of \d+ measured searches tell the positives from the negatives$/,
    );
    await expect(result.getByTestId("separation-requests")).toHaveText(
      /^\d+ of \d+ requests$/,
    );

    const question =
      (await card.getByTestId("separation-question").textContent()) ?? "";
    const offered = numberOf(/in ([\d,]+) genes\?$/.exec(question)?.[1] ?? "");
    await card.getByRole("button", { name: "Yes", exact: true }).click();
    await expect(card.getByTestId("separation-decision")).toHaveText("You said yes.", {
      timeout: 90_000,
    });

    await expect(page.getByTestId("data-graph-snapshot")).not.toHaveCount(0, {
      timeout: 240_000,
    });
    await expect(
      page.getByTestId("task-row").filter({ hasText: "Run control tests" }),
    ).not.toHaveCount(0, { timeout: 120_000 });
    const evidence = page
      .getByTestId("data-evidence-card")
      .filter({ has: page.getByTestId("evidence-controls") });
    await expect(evidence).toHaveCount(1, { timeout: TASK_BUDGET_MS });
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });

    const layout = layoutOf(await readNodes(apiClient, id));
    expect(layout.steps).toBeGreaterThan(0);
    const counts = await expectBuild(page, apiClient, id, siteId, layout);
    expect(counts.root).toBe(offered);
    await expect(evidence.getByTestId("figure-caption")).toContainText(
      `${recovered} of ${positives} positive controls returned`,
    );
    await expect(evidence.getByTestId("figure-caption")).toContainText(
      `${admitted} of ${negatives} negative controls returned`,
    );
    await expectStepTable(evidence, counts);
  });

  test("V5 - A no with a comment", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    test.setTimeout(900_000);
    await chatPage.startOn(siteId);
    const id = chatPage.lastStrategyId ?? "";
    const { card } = await runSeparation(chatPage, page, siteId);

    await card
      .getByRole("textbox", { name: "Why not" })
      .fill("Too broad for a vaccine screen.");
    await card.getByRole("button", { name: "No", exact: true }).click();
    await expect(card.getByTestId("separation-decision")).toHaveText("You said no.", {
      timeout: 90_000,
    });
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });
    await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
    await graphPage.showRailStrategy();
    await expect(graphPage.railEmptyHeading).toBeVisible();
  });

  test("V7 - Compare two variants of a search", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await chatPage.sendAndSettle(
      prompt(
        "variants",
        "Compare the SignalP-6.0 and SignalP-4.1 versions of this search.",
      ),
    );
    const figure = page.getByTestId("data-variant-comparison");
    await expect(figure).toHaveCount(1, { timeout: 120_000 });
    await expect(figure).toContainText("Variants");
    await expect(figure.getByRole("columnheader")).toHaveText([
      "Variant",
      "Genes",
      "Unique to it",
    ]);
    const variants = await bodyCells(figure);
    expect(variants.length).toBeGreaterThan(1);
    const largest = Math.max(...variants.map((row) => numberOf(row[1] ?? "")));
    await expect(figure.getByTestId("figure-caption")).toHaveText(
      new RegExp(
        `^Table \\d+\\. ${variants.length} variants, ${printed(largest)} genes in the largest$`,
      ),
    );
    await expect(figure).toContainText(/ vs .+:\s*[\d,]+ shared, Jaccard /);

    const reply = chatPage.assistantMessages.filter({ has: figure });
    await openTrace(reply);
    await expect(traceRows(reply, "Compare variants")).not.toHaveCount(0);
  });
});
