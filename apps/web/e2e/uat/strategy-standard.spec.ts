/**
 * UAT flows S1 to S16: building strategies the standard way. Every count is
 * read from the site at run time and compared with the thread, the rail and
 * the canvas; only the model is mocked.
 */

import type { Page } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { combineNode } from "../fixtures/ast";
import {
  LAYOUTS,
  ORTHOLOGS,
  SIGNAL_PEPTIDE,
  TRANSMEMBRANE,
  layoutOf,
} from "../fixtures/arc-layouts";
import {
  expectBuild,
  expectEvidence,
  openTrace,
  sampledGeneIds,
  traceRows,
} from "../fixtures/build-checks";
import {
  countPattern,
  printed,
  readConversation,
  readNodes,
  siteControlSets,
  siteCounts,
  siteGeneIdPrefix,
  siteOrganism,
} from "../fixtures/site-reads";
import {
  buildOn,
  expectCountAnswered,
  nodeBySearch,
  openCanvas,
  paramText,
} from "../fixtures/strategy-builds";

const S1_TEXT = (organism: string) =>
  `Find ${organism} genes whose proteins have a predicted signal peptide.`;
const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;
const S3_TEXT = (organism: string) =>
  `Find ${organism} genes that have a predicted signal peptide or 2 to 99 transmembrane domains.`;
const S4_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide, excluding any gene with 2 to 99 transmembrane domains.`;
/** The saved-strategies row named `name`. */
function savedRow(page: Page, name: string) {
  return page
    .getByTestId("saved-strategies-list")
    .getByRole("listitem")
    .filter({ hasText: name });
}

test.describe("Standard strategy flows", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("S1 - One search", async ({ chatPage, apiClient, page, siteId }) => {
    const organism = siteOrganism(siteId);
    const id = await buildOn(chatPage, siteId, prompt("single", S1_TEXT(organism)));

    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    await expectEvidence(page, "Supported", counts.root);
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);

    const leaf = nodeBySearch(await readNodes(apiClient, id), SIGNAL_PEPTIDE);
    expect(paramText(leaf, "organism")).toContain(organism);

    const reply = chatPage.assistantReply(countPattern(counts.root));
    await openTrace(reply);
    await expect(reply.getByTestId("trace-group-label")).toContainText([
      "Planning",
      "Checking",
    ]);
    await expect(traceRows(reply, "Choose a search")).not.toHaveCount(0);
    await expect(
      traceRows(reply, "Choose a search").getByTestId("trace-row-summary"),
    ).toContainText([/genes/]);
  });

  test("S2 - Two searches, INTERSECT", async ({
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
    const nodes = await readNodes(apiClient, id);
    const inputs = [SIGNAL_PEPTIDE, TRANSMEMBRANE].map(
      (name) => counts.byStep[nodeBySearch(nodes, name).id ?? ""] ?? -1,
    );
    for (const input of inputs) expect(input).toBeGreaterThanOrEqual(counts.root);

    const card = await expectEvidence(page, "Supported", counts.root);
    const statuses = card.getByTestId("evidence-requirement-status");
    await expect(statuses).not.toHaveCount(0);
    for (const status of await statuses.allTextContents()) expect(status).toBe("Met");
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);
  });

  test("S3 - UNION", async ({ chatPage, graphPage, apiClient, page, siteId }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("union", S3_TEXT(siteOrganism(siteId))),
    );

    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.union);
    const nodes = await readNodes(apiClient, id);
    for (const name of [SIGNAL_PEPTIDE, TRANSMEMBRANE]) {
      expect(counts.byStep[nodeBySearch(nodes, name).id ?? ""]).toBeLessThanOrEqual(
        counts.root,
      );
    }
    await openCanvas(graphPage, siteId, id);
    await expect(page.getByTestId("combine-operator-badge")).toHaveText("Union");
  });

  test("S4 - MINUS", async ({ chatPage, graphPage, apiClient, page, siteId }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("minus", S4_TEXT(siteOrganism(siteId))),
    );

    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.minus);
    const signal = nodeBySearch(await readNodes(apiClient, id), SIGNAL_PEPTIDE);
    expect(counts.byStep[signal.id ?? ""]).toBeGreaterThanOrEqual(counts.root);
    await openCanvas(graphPage, siteId, id);
    await expect(page.getByTestId("combine-operator-badge")).toHaveText("Minus");
  });

  test("S5 - Orthology transform", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const organism = siteOrganism(siteId);
    const id = await buildOn(chatPage, siteId, prompt("intersect", S2_TEXT(organism)));
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

    await chatPage.sendAndSettle(
      prompt("orthologs", "Carry these to their orthologs in the related species."),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.orthologs);
    const transform = nodeBySearch(await readNodes(apiClient, id), ORTHOLOGS);
    expect(paramText(transform, "isSyntenic")).toBe("no");
    expect(paramText(transform, "organism")).not.toBe("");
    expect(paramText(transform, "organism")).not.toContain(organism);
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);

    await openCanvas(graphPage, siteId, id);
    await graphPage.clickNode(transform.id ?? "");
    await graphPage.expectEditorSheetOpen();
    await expect(graphPage.editorSheet).toContainText("Syntenic Orthologs Only?");
  });

  test("S6 - The round trip that keeps the source organism", async ({
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
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

    await chatPage.sendAndSettle(
      prompt(
        "round-trip",
        "Keep only those with syntenic orthologs in the related species.",
      ),
    );
    const counts = await expectBuild(
      page,
      apiClient,
      id,
      siteId,
      LAYOUTS["round-trip"],
    );
    const transforms = (await readNodes(apiClient, id)).filter(
      (node) => node.searchName === ORTHOLOGS,
    );
    expect(transforms.map((node) => paramText(node, "isSyntenic"))).toEqual([
      "yes",
      "yes",
    ]);
    expect(transforms.map((node) => paramText(node, "organism"))).toContain(
      siteOrganism(siteId),
    );

    const card = await expectEvidence(page, /Supported|Not supported/, counts.root);
    const genes = await sampledGeneIds(card);
    expect(genes.length).toBeGreaterThan(0);
    for (const gene of genes)
      expect(gene.startsWith(siteGeneIdPrefix(siteId))).toBe(true);
  });

  test("S7 - A saved strategy used in another conversation", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const name = "UAT saved S7";
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    const rootId = (await readConversation(apiClient, id)).rootStepId ?? "";

    await page.getByTestId(`compact-step-kebab-${rootId}`).click();
    await page.getByRole("menuitem", { name: "Save as reusable..." }).click();
    const dialog = page.getByTestId("save-substrategy-dialog");
    await expect(dialog.getByRole("heading")).toHaveText("Save as reusable strategy");
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByTestId("save-substrategy-confirm").click();
    await expect(dialog).toHaveCount(0, { timeout: 60_000 });

    await page.goto(`/${siteId}/saved`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Saved strategies",
    );
    const row = savedRow(page, name);
    await expect(row).toContainText(`3 steps · ${printed(counts.root)} genes`, {
      timeout: 30_000,
    });

    const use = row.getByRole("button", { name: "Use in a new conversation" });
    await use.click();
    await expect(page.getByText("Inserted into a new conversation")).toBeVisible({
      timeout: 60_000,
    });
    await page.waitForURL(/\/conversation\/[0-9a-f-]{36}$/, { timeout: 60_000 });
    await graphPage.openRailStrategyPanel();
    await expect(graphPage.railPanel).toContainText(printed(counts.root));

    await chatPage.newChat(siteId);
    await graphPage.showRailStrategy();
    await expect(graphPage.railEmptyHeading).toBeVisible();
    await page.getByTestId("rail-strategy-insert-saved").click();
    const insert = page.getByTestId("insert-saved-dialog");
    await insert.getByRole("button").filter({ hasText: name }).click();
    await insert.getByTestId("insert-saved-confirm").click();
    await expect(page.getByText("Saved strategy inserted")).toBeVisible({
      timeout: 60_000,
    });

    await page.goto(`/${siteId}/saved`);
    await expect(savedRow(page, name)).toContainText("Used in 2 conversations", {
      timeout: 30_000,
    });
    const remove = savedRow(page, name).getByRole("button", {
      name: "Delete saved strategy",
    });
    await expect(remove).toBeDisabled();
    await expect(remove).toHaveAttribute(
      "title",
      "Used in 2 conversations; remove it from them before deleting it.",
    );
  });

  test("S8 - A strategy made on the site, opened in PathFinder", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const madeIn = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, madeIn, siteId, LAYOUTS.single);
    const wdkStrategyId =
      (await readConversation(apiClient, madeIn)).wdkStrategyId ?? 0;
    expect(wdkStrategyId).toBeGreaterThan(0);
    // The conversation goes and the strategy stays in the account, as one made on the site.
    const dropped = await apiClient.delete(`/api/v1/conversations/${madeIn}`);
    expect(dropped.ok(), `delete ${dropped.status()}`).toBe(true);

    await page.goto(`/${siteId}/conversation`);
    await page.getByTestId("conversations-new-assistant-button").click();
    await page.getByTestId("open-wdk-strategy-menu-item").click();
    const dialog = page.getByTestId("open-wdk-strategy-dialog");
    await expect(dialog.getByRole("heading")).toHaveText("Open a VEuPathDB strategy");
    const pick = dialog.getByTestId(`open-wdk-strategy-pick-${wdkStrategyId}`);
    await expect(pick).toContainText(`${printed(counts.root)} results`, {
      timeout: 60_000,
    });

    const other = siteId === "toxodb" ? "plasmodb" : "toxodb";
    const otherHost =
      other === "toxodb" ? "https://toxodb.org/toxo" : "https://plasmodb.org/plasmo";
    const otherName = other === "toxodb" ? "ToxoDB" : "PlasmoDB";
    await dialog
      .getByTestId("open-wdk-strategy-input")
      .fill(`${otherHost}/app/workspace/strategies/214626640`);
    await expect(dialog.getByTestId("open-wdk-strategy-notice")).toHaveText(
      `That link names a ${otherName} strategy. Switch to ${otherName} to open it.`,
    );
    await expect(dialog.getByTestId("open-wdk-strategy-confirm")).toBeDisabled();
    await dialog.getByTestId("open-wdk-strategy-input").fill("");

    await pick.click();
    await dialog.getByTestId("open-wdk-strategy-confirm").click();
    await expect(page.getByText("Strategy opened")).toBeVisible({ timeout: 60_000 });
    await page.waitForURL(/\/conversation\/[0-9a-f-]{36}$/, { timeout: 60_000 });
    const opened = new URL(page.url()).pathname.split("/").pop() ?? "";
    chatPage.lastStrategyId = opened;
    expect((await readConversation(apiClient, opened)).wdkStrategyId).toBe(
      wdkStrategyId,
    );

    expect(await expectCountAnswered(chatPage, apiClient, opened, siteId)).toBe(
      counts.root,
    );
  });

  test("S9 - Edit a parameter", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("minus", S4_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.minus);
    const before = await readConversation(apiClient, id);
    const signalBefore = (before.steps ?? []).find(
      (s) => s.searchName === SIGNAL_PEPTIDE,
    );
    const tmBefore = nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE);

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
      .not.toBe(paramText(tmBefore, "min_tm"));
    const edited = await expectBuild(page, apiClient, id, siteId, LAYOUTS.minus);
    const after = await readConversation(apiClient, id);
    const signalAfter = (after.steps ?? []).find(
      (s) => s.searchName === SIGNAL_PEPTIDE,
    );
    expect(signalAfter?.wdkStepId).toBe(signalBefore?.wdkStepId);
    await expect(chatPage.assistantReply(countPattern(edited.root))).not.toHaveCount(0);

    await openCanvas(graphPage, siteId, id);
    const tm = nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE);
    await graphPage.clickNode(tm.id ?? "");
    await graphPage.expectEditorSheetOpen();
    const minimum = graphPage.editorSheet.locator('input[name="min_tm"]');
    await minimum.fill(paramText(tmBefore, "min_tm"));
    await graphPage.saveEditor();
    await expect
      .poll(async () =>
        paramText(
          nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE),
          "min_tm",
        ),
      )
      .toBe(paramText(tmBefore, "min_tm"));

    await page.goto(`/${siteId}/conversation/${id}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    const handEdited = await expectCountAnswered(chatPage, apiClient, id, siteId);
    expect(handEdited).not.toBe(edited.root);
  });

  test("S10 - Add a step", async ({ chatPage, apiClient, page, siteId }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    const before = await readConversation(apiClient, id);
    const keptIds = (before.steps ?? []).map((step) => step.wdkStepId);

    await chatPage.sendAndSettle(
      prompt(
        "add-step",
        "Also keep only those predicted to be exported to the host cell.",
      ),
    );
    await expect
      .poll(async () => layoutOf(await readNodes(apiClient, id)).steps, {
        timeout: 60_000,
      })
      .toBe(5);
    const layout = layoutOf(await readNodes(apiClient, id));
    expect(layout.operators).toEqual(["INTERSECT", "INTERSECT"]);
    const counts = await expectBuild(page, apiClient, id, siteId, layout);
    const after = await readConversation(apiClient, id);
    const afterIds = (after.steps ?? []).map((step) => step.wdkStepId);
    for (const kept of keptIds.filter((wdk) => wdk != null))
      expect(afterIds).toContain(kept);
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);
  });

  test("S11 - Delete a step", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("minus", S4_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.minus);

    await chatPage.sendAndSettle(
      prompt("delete-step", "Remove the transmembrane-domain step."),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    await expect(page.getByTestId("approval-card")).toHaveCount(0);
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);

    const canvasId = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, canvasId, siteId, LAYOUTS.intersect);
    await openCanvas(graphPage, siteId, canvasId);
    const tm = nodeBySearch(await readNodes(apiClient, canvasId), TRANSMEMBRANE);
    await graphPage.deleteStep(tm.id ?? "");
    await expect
      .poll(async () => layoutOf(await readNodes(apiClient, canvasId)), {
        timeout: 60_000,
      })
      .toEqual(LAYOUTS.single);
    await expect(graphPage.strategyPageStepCount).toHaveText("1 step");
  });

  test("S12 - Replace a subtree", async ({ chatPage, apiClient, page, siteId }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

    await chatPage.sendAndSettle(
      prompt(
        "replace-subtree",
        "Replace the transmembrane-domain search with the exported-protein prediction.",
      ),
    );
    // The mock's replace is a chat edit, so no approval card asks first.
    await expect(page.getByTestId("approval-card")).toHaveCount(0);
    // The replacing search is the site's own, so the check names the one it replaced.
    await expect
      .poll(async () => layoutOf(await readNodes(apiClient, id)).searches, {
        timeout: 120_000,
      })
      .not.toContain(TRANSMEMBRANE);
    const layout = layoutOf(await readNodes(apiClient, id));
    expect(layout.steps).toBe(3);
    expect(layout.searches).toContain(SIGNAL_PEPTIDE);
    expect(layout.operators).toEqual(["INTERSECT"]);
    const counts = await expectBuild(page, apiClient, id, siteId, layout);
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);
  });

  test("S13 - Clear", async ({ chatPage, graphPage, apiClient, page, siteId }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    const clearMessage =
      "Clear the current strategy by calling clear_strategy with confirm=true.";

    await chatPage.messageInput.fill("/clear");
    await chatPage.messageInput.press("Enter");
    await expect(chatPage.userMessage(clearMessage)).toHaveCount(1, {
      timeout: 30_000,
    });
    const approval = page.getByTestId("approval-card");
    await expect(approval.getByTestId("approval-card-title")).toHaveText(
      "Clear the strategy? This removes every step from this conversation and from VEuPathDB.",
      { timeout: 120_000 },
    );
    await expect(page.getByTestId("turn-trace-summary")).toContainText([
      "Waiting for you",
    ]);
    await approval.getByTestId("tool-approval-deny").click();
    await expect(page.getByTestId("tool-approval-decision")).toHaveText("Denied");
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });
    expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.single);

    await chatPage.messageInput.fill("/clear");
    await chatPage.messageInput.press("Enter");
    await expect(approval.getByTestId("approval-card-title")).toBeVisible({
      timeout: 120_000,
    });
    await approval.getByTestId("tool-approval-approve").click();
    await expect(page.getByTestId("data-graph-cleared")).toContainText(
      "Strategy cleared - user cleared the strategy",
      { timeout: 120_000 },
    );
    await graphPage.showRailStrategy();
    await expect(graphPage.railEmptyHeading).toBeVisible();
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
  });

  test("S14 - A count question builds", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt(
        "count-question",
        `How many protein-coding genes does ${siteOrganism(siteId)} have?`,
      ),
    );
    const counts = await expectBuild(
      page,
      apiClient,
      id,
      siteId,
      LAYOUTS["count-question"],
    );
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);
  });

  test("S15 - A question about one gene does not build", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const [gene] = siteControlSets(siteId).flatMap((set) => set.positive_ids);
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("gene-question", `What does ${gene ?? ""} do?`),
    );
    // The literature figure needs the research tool source, which the e2e stack does not start.
    await expect(chatPage.assistantMessages).toHaveCount(1);
    await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
    await graphPage.showRailStrategy();
    await expect(graphPage.railEmptyHeading).toBeVisible();
  });

  test("S16 - Change an operator on the canvas", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    const built = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    const combine = await combineNode(
      await apiClient.get(`/api/v1/conversations/${id}/ast`),
    );

    await openCanvas(graphPage, siteId, id);
    await graphPage.changeOperator(combine.id ?? "", "UNION");
    await expect(page.getByTestId("combine-operator-badge")).toHaveText("Union");
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );
    const union = await siteCounts(apiClient, id, siteId);
    expect(union.root).toBeGreaterThanOrEqual(built.root);
    expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.union);

    await page.goto(`/${siteId}/conversation/${id}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    expect(await expectCountAnswered(chatPage, apiClient, id, siteId)).toBe(union.root);
  });
});
