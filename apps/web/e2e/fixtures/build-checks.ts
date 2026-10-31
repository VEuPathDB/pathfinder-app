/**
 * What every build shows, asserted against what the site answers: the stored
 * layout, the facts' result count, the rail's step list and the
 * evidence card. The counts are read from the site at run time.
 */

import { type Locator, type Page, expect } from "@playwright/test";

import type { ApiClient } from "./api-client";
import { type Layout, layoutOf } from "./arc-layouts";
import { printed, siteCounts, type SiteCounts, storedNodes } from "./site-reads";
import { GraphPage } from "../pages/graph.page";

const LAYOUT_BUDGET_MS = 60_000;

/** The facts figures that state `genes` as the strategy's result. */
export function resultFigure(page: Page, genes: number): Locator {
  return page.getByTestId("data-facts").filter({
    has: page.locator(`[data-testid="facts-root-count"][data-count="${genes}"]`),
  });
}

/**
 * Open every trace of one reply. A settled trace mounts collapsed, and its rows
 * leave the accessibility tree until it is opened; a reply that resumed after
 * a card holds one trace per run.
 */
export async function openTrace(reply: Locator): Promise<void> {
  const toggles = reply.getByTestId("turn-trace-toggle");
  await expect(toggles).not.toHaveCount(0, { timeout: 30_000 });
  const closed = reply.locator(
    '[data-testid="turn-trace-toggle"][aria-expanded="false"]',
  );
  await closed.evaluateAll((buttons) => {
    for (const button of buttons) (button as HTMLButtonElement).click();
  });
  await expect(closed).toHaveCount(0);
}

/** The trace rows of one reply whose label is `label`. */
export function traceRows(reply: Locator, label: string): Locator {
  return reply.getByTestId("trace-row").filter({ hasText: label });
}

/**
 * Wait until the stored tree has `layout`, then assert the figure, the rail and
 * the root row read the count the site answers for it. Returns those counts.
 */
export async function expectBuild(
  page: Page,
  api: ApiClient,
  conversationId: string,
  siteId: string,
  layout: Layout,
): Promise<SiteCounts> {
  await expect
    .poll(async () => layoutOf(await storedNodes(api, conversationId)), {
      timeout: LAYOUT_BUDGET_MS,
    })
    .toEqual(layout);
  const counts = await siteCounts(api, conversationId, siteId);

  await expect(resultFigure(page, counts.root)).not.toHaveCount(0);

  const graph = new GraphPage(page);
  await graph.openRailStrategyPanel();
  await expect(graph.railFooter).toHaveText(
    `${layout.steps} ${layout.steps === 1 ? "step" : "steps"}`,
  );
  await expect(graph.railStepRows).toHaveCount(layout.steps);
  await expect(graph.railPanel).toContainText(printed(counts.root));
  return counts;
}

/** The evidence card of a check that states the root count, and no verdict. */
export async function expectEvidence(page: Page, rootCount: number): Promise<Locator> {
  const card = page.getByTestId("data-evidence-card").filter({
    has: page.getByTestId("evidence-steps").filter({ hasText: printed(rootCount) }),
  });
  await expect(card).not.toHaveCount(0, { timeout: 60_000 });
  await expect(card.getByTestId("evidence-verdict")).toHaveCount(0);
  return card;
}

/** The card lists the site's checks, and the site answered every one without a failure. */
export async function expectNoCheckFailed(card: Locator): Promise<void> {
  const results = card.getByTestId("evidence-check").locator("td:nth-child(2)");
  await expect(results).not.toHaveCount(0);
  for (const result of await results.allTextContents())
    expect(result.trim()).not.toMatch(/^(Failed|No answer from the site)$/);
}

/**
 * The check's controls caveat as the ledger words it: the positives returned
 * when one is missed, the negatives returned when one comes back.
 */
export function controlsCaveat(
  recovered: number,
  positives: number,
  admitted: number,
  negatives: number,
): string {
  return [
    ...(recovered < positives
      ? [`${recovered} of ${positives} positive controls returned`]
      : []),
    ...(admitted > 0 ? [`${admitted} of ${negatives} negative controls returned`] : []),
  ].join("; ");
}

/** The gene ids an evidence card's sampled-gene table lists, one per body row. */
export async function sampledGeneIds(card: Locator): Promise<string[]> {
  return card
    .getByTestId("evidence-sampled-genes")
    .locator("tbody tr")
    .evaluateAll((rows) =>
      rows.map((row) => row.querySelector("td")?.textContent.trim() ?? ""),
    );
}
