/**
 * The wrong-path arcs: a `[[fault:<name>]]` token makes the mock send one wrong
 * call in place of the arc's, and each test asserts the guard's reaction the
 * researcher sees, then the state the corrected turn leaves.
 */

import type { Locator, Page } from "@playwright/test";
import type { EdaStudyListResponse } from "@pathfinder/shared/generated/types/EdaStudyListResponse";

import { test, expect } from "../fixtures/test";
import { type ArcName, prompt } from "../fixtures/arcs";
import { type ApiClient, fetchConversationMessages } from "../fixtures/api-client";
import { LAYOUTS, ORTHOLOGS, layoutOf } from "../fixtures/arc-layouts";
import { expectBuild, expectEvidence, openTrace } from "../fixtures/build-checks";
import {
  printed,
  readConversation,
  readNodes,
  siteControlSets,
  siteOrganism,
} from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";

type FaultName =
  | "syntenic-left-off"
  | "repeat-control-test"
  | "transcript-count"
  | "all-unclear"
  | "sweep-without-controls"
  | "long-reason"
  | "short-card-reply"
  | "unlisted-search"
  | "value-as-term"
  | "off-vocabulary"
  | "unbacked-controls"
  | "misstated-count"
  | "misnamed-deletion";

const TURN_BUDGET_MS = 600_000;
const CONTRACT = /^This reply does not match what the turn did:/;

const S1_TEXT = (organism: string) =>
  `Find ${organism} genes whose proteins have a predicted signal peptide.`;
const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;

/** The arc's message with the fault token after the arc token. */
function faulted(arcName: ArcName, fault: FaultName, text: string): string {
  return `${prompt(arcName, text)}[[fault:${fault}]]`;
}

/** Open the trace of every reply on the thread. */
async function openTraces(chatPage: ChatPage): Promise<void> {
  for (const reply of await chatPage.assistantMessages.all()) {
    await openTrace(reply);
  }
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

/** The trace rows labelled `label` whose status is `error`. */
function errorRows(page: Page, label: string): Locator {
  return page
    .getByTestId("trace-row")
    .filter({ hasText: label })
    .filter({
      has: page.locator('[data-testid="trace-row-status"][data-status="error"]'),
    });
}

/** Start on `siteId`, send one message, wait out its turn, return the conversation. */
async function sendOn(
  chatPage: ChatPage,
  siteId: string,
  message: string,
): Promise<string> {
  await chatPage.startOn(siteId);
  await chatPage.sendAndSettle(message);
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  return id;
}

interface LoggedChunk {
  type: string;
  errorText?: string;
  data?: { state?: string; resultSummary?: string | null };
}

/**
 * Every refusal the conversation logged, in full: a tool's error and a failed
 * sub-agent step. The trace clips a summary, so a guard's own sentence is read here.
 */
async function loggedRefusals(api: ApiClient, conversationId: string): Promise<string> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/events/snapshot`);
  expect(resp.status(), `events of ${conversationId}`).toBe(200);
  const { chunks } = (await resp.json()) as { chunks: LoggedChunk[] };
  return chunks
    .map((chunk) =>
      chunk.data?.state === "failed"
        ? (chunk.data.resultSummary ?? "")
        : (chunk.errorText ?? ""),
    )
    .filter((text) => text !== "")
    .join("\n");
}

/** The contract's correction is on the thread, as a "Final result" error row. */
async function expectCorrection(page: Page): Promise<void> {
  await expect(
    errorRows(page, "Final result")
      .getByTestId("trace-row-summary")
      .filter({ hasText: CONTRACT }),
  ).not.toHaveCount(0);
}

/** Every assistant reply of the conversation as the event log holds it, joined. */
async function replyText(api: ApiClient, conversationId: string): Promise<string> {
  const messages = await fetchConversationMessages(api, conversationId);
  return messages
    .filter((message) => message.role === "assistant")
    .map((message) => message.content)
    .join("\n");
}

/** The site's signal peptide control set, else its first. */
function controlSet(siteId: string) {
  const sets = siteControlSets(siteId);
  const chosen = sets.find((set) => /signal peptide/i.test(set.name)) ?? sets[0];
  if (chosen === undefined) throw new Error(`the ${siteId} seeds carry no control set`);
  return chosen;
}

function controlLines(siteId: string): string {
  const set = controlSet(siteId);
  return [
    `Positive controls: ${set.positive_ids.join(" ")}`,
    `Negative controls: ${set.negative_ids.join(" ")}`,
  ].join("\n");
}

test.describe("Fault arcs", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: TURN_BUDGET_MS });

  test("A search the listing never named is refused", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("single", "unlisted-search", S1_TEXT(siteOrganism(siteId))),
    );

    await openTraces(chatPage);
    const refused = errorRows(page, "Choose a search");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^search_name='GenesByNoSuchSearch' is not a known value for set_criterion\./,
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
  });

  test("A value passed as a parameter term is refused", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const organism = siteOrganism(siteId);
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("single", "value-as-term", S1_TEXT(organism)),
    );

    await openTraces(chatPage);
    const refused = errorRows(page, "Choose a search");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      new RegExp(`: ${organism} is a value this call sets on `),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
  });

  test("A value the vocabulary does not list is refused", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("single", "off-vocabulary", S1_TEXT(siteOrganism(siteId))),
    );

    await openTraces(chatPage);
    const refused = errorRows(page, "Choose a search");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^organism on GenesWithSignalPeptide has no entry matching \['Organismus fictus'\]\./,
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
  });

  test("FND-10 - a reason past its cap stops the pass, and the pass is continued", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("intersect", "long-reason", S2_TEXT(siteOrganism(siteId))),
    );

    await openTraces(chatPage);
    // The fourth refusal ends the pass before its row is drawn, so three show.
    const refused = errorRows(page, "Choose a search");
    await expect(refused).toHaveCount(3);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      Array.from({ length: 3 }, () => /^tm_domains: the reason must hold the term /),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
  });

  test("FND-5 - a gene count named in transcripts is corrected", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("single", "transcript-count", S1_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await openTraces(chatPage);
    await expectCorrection(page);
    const root = printed(counts.root);
    expect(await loggedRefusals(apiClient, id)).toContain(
      `your reply writes ${root} transcripts. Write ${root} genes.`,
    );
    const reply = await replyText(apiClient, id);
    expect(reply).toContain(`${root} genes`);
    expect(reply).not.toMatch(/transcripts/);
  });

  test("A count no step holds is corrected to the root", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("single", "misstated-count", S1_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await openTraces(chatPage);
    await expectCorrection(page);
    expect(await loggedRefusals(apiClient, id)).toContain(
      `Your reply states ${printed(2 * counts.root + 1)} genes for the strategy, and no step of it holds that count`,
    );
    const reply = await replyText(apiClient, id);
    expect(reply).toContain(`returns ${printed(counts.root)} genes`);
    expect(reply).not.toContain(`${printed(2 * counts.root + 1)} genes`);
  });

  test("FND-6 - every sampled gene unclear reads as unclear", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted("single", "all-unclear", S1_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    const card = await expectEvidence(page, "Supported", counts.root);
    const sampled = card.getByTestId("evidence-sampled-genes");
    const rows = await sampled.locator("tbody tr").count();
    expect(rows).toBeGreaterThan(0);
    await expect(card.getByTestId("evidence-sample-count")).toHaveText(
      `${rows} of ${rows} sampled ${rows === 1 ? "gene" : "genes"} unclear`,
    );
  });

  test("FND-2 - a repeated control test is answered from the first", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await chatPage.sendAndSettle(
      faulted(
        "controls-test",
        "repeat-control-test",
        `Test this strategy against my controls.\n${controlLines(siteId)}`,
      ),
    );
    const card = page
      .getByTestId("data-evidence-card")
      .filter({ has: page.getByTestId("evidence-controls") });
    await expect(card).toHaveCount(1, { timeout: TURN_BUDGET_MS });
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });

    await expect(
      page.getByTestId("task-row").filter({ hasText: "Run control tests" }),
    ).toHaveCount(1);
    await openTraces(chatPage);
    await expect(
      page
        .getByTestId("trace-row-summary")
        .filter({ hasText: /^Already tested on this step:/ }),
    ).toHaveCount(1);
    const rows = await bodyCells(card.getByTestId("evidence-controls"));
    const positive = rows.find((cells) => cells[0] === "Positive") ?? [];
    expect(positive[1]).toBe(printed(controlSet(siteId).positive_ids.length));
  });

  test("A control count no test holds is corrected", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await chatPage.sendAndSettle(
      faulted(
        "controls-test",
        "unbacked-controls",
        `Test this strategy against my controls.\n${controlLines(siteId)}`,
      ),
    );
    await expect(
      page
        .getByTestId("data-evidence-card")
        .filter({ has: page.getByTestId("evidence-controls") }),
    ).toHaveCount(1, { timeout: TURN_BUDGET_MS });
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });

    await openTraces(chatPage);
    await expectCorrection(page);
    const claimed = controlSet(siteId).positive_ids.length + 1;
    expect(await loggedRefusals(apiClient, id)).toContain(
      `The reply says ${claimed} of ${claimed} positive controls returned`,
    );
    expect(await replyText(apiClient, id)).not.toContain(
      `${claimed} of ${claimed} positive controls`,
    );
  });

  test("FND-8 - a sweep that names no controls is refused before its card", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);

    await chatPage.send(
      faulted(
        "sweep",
        "sweep-without-controls",
        `Optimize the SignalP version of the signal peptide search to recover as many of my positive controls as possible while returning as few of my negative controls as possible.\n${controlLines(siteId)}`,
      ),
    );
    const approval = page.getByTestId("approval-card");
    await expect(approval.getByTestId("approval-card-title")).toHaveText(
      "Optimize parameters needs your approval before it runs.",
      { timeout: 240_000 },
    );
    await expect(approval).toHaveCount(1);
    await openTraces(chatPage);
    const refused = errorRows(page, "Optimize parameters");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^A sweep scores each setting against the controls, and this call names none\./,
    );

    await approval.getByTestId("tool-approval-deny").click();
    await expect(page.getByTestId("tool-approval-decision")).toContainText("Denied");
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });
    await expect(
      page.getByTestId("task-row").filter({ hasText: "Optimize parameters" }),
    ).toHaveCount(0);
  });

  test("FND-14 - a card whose reply is shorter than a sentence is refused", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    const id = chatPage.lastStrategyId ?? "";
    await chatPage.send(
      faulted(
        "consult",
        "short-card-reply",
        "Find drug targets that are expressed in the blood stage and have no human equivalent.",
      ),
    );

    const carousel = page.getByTestId("consult-carousel");
    await expect(carousel).toBeVisible({ timeout: 240_000 });
    await expect(carousel).toHaveCount(1);
    await openTraces(chatPage);
    const refused = errorRows(page, "Ask you");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^1 validation error/,
    );
    expect(await loggedRefusals(apiClient, id)).toContain(
      "String should have at least 20 characters",
    );
    await expect(chatPage.assistantReply(/Two choices shape the steps/)).toHaveCount(1);
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
  });

  test("FND-7 - a reply naming a step the delete left standing is corrected", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

    await chatPage.send(
      faulted(
        "delete-step-card",
        "misnamed-deletion",
        "Remove the transmembrane domains step.",
      ),
    );
    const approval = page.getByTestId("approval-card");
    await expect(approval.getByTestId("approval-card-title")).toHaveText(
      /^Delete step '.+' \(GenesByTransmembraneDomains, .+\)\?$/,
      { timeout: 240_000 },
    );
    await approval.getByTestId("tool-approval-approve").click();
    await expect(page.getByTestId("tool-approval-decision")).toContainText("Approved");
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });

    await openTraces(chatPage);
    await expectCorrection(page);
    expect(await loggedRefusals(apiClient, id)).toContain(
      "Your reply says it removed the signal peptide step, and that step is still in the strategy.",
    );
    const reply = await replyText(apiClient, id);
    expect(reply).toContain("Removed the transmembrane domains step");
    expect(reply).not.toContain("Removed the signal peptide step");
    expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.single);
  });

  test("FND-4 - a cross-organism INTERSECT is refused before any step", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      prompt(
        "cross-organism",
        `Intersect the ${siteOrganism(siteId)} genes that have a predicted signal peptide with the genes of a related species that have a predicted signal peptide.`,
      ),
    );

    await openTraces(chatPage);
    const refused = errorRows(page, "Arrange the steps");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^The structure is refused: Cannot INTERSECT steps with different organism scopes/,
    );
    await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
  });

  test("FND-12 - an organism another site holds is routed to the portal", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const other = siteId === "toxodb" ? "plasmodb" : "toxodb";
    const id = await sendOn(
      chatPage,
      siteId,
      prompt(
        "portal-only",
        `Carry these to their orthologs in ${siteOrganism(other)}.`,
      ),
    );

    await openTraces(chatPage);
    await expect(errorRows(page, "Choose a search")).toHaveCount(1);
    await expect(
      chatPage.assistantMessages.locator('a[href="/veupathdb/conversation"]'),
    ).toHaveCount(1);
    await expect(page.getByTestId("approval-card")).toHaveCount(0);
    await expect(page.getByTestId("consult-carousel")).toHaveCount(0);
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
  });

  test("FND-11 - a study another site publishes is not opened", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    // With no study index the search matches by name, so the message is a
    // study's name: the first of the site's catalog another site publishes.
    const resp = await apiClient.get(`/api/v1/eda/studies?siteId=${siteId}&limit=100`);
    expect(resp.status()).toBe(200);
    const { studies } = (await resp.json()) as EdaStudyListResponse;
    const elsewhere = studies.find(
      (study) => study.sites.length > 0 && !study.sites.includes(siteId),
    );
    if (elsewhere === undefined) {
      throw new Error(`no study of the ${siteId} catalog is published on another site`);
    }
    const id = await sendOn(
      chatPage,
      siteId,
      prompt("eda-other-site", elsewhere.displayName),
    );

    await openTraces(chatPage);
    const refused = errorRows(page, "Open study");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^This study is on .+; its genes are not .+ genes\./,
    );
    expect(await loggedRefusals(apiClient, id)).toContain("Nothing was opened.");
    await expect(page.getByTestId("data-eda-analysis-state")).toHaveCount(0);
    expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
  });

  test("FND-1 - a syntenic request that leaves synteny off is refused", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const id = await sendOn(
      chatPage,
      siteId,
      faulted(
        "syntenic-orthologs",
        "syntenic-left-off",
        `${S2_TEXT(siteOrganism(siteId))} Then carry them to their syntenic orthologs in a related species.`,
      ),
    );

    await openTraces(chatPage);
    const refused = errorRows(page, "Choose a search");
    await expect(refused).toHaveCount(1);
    await expect(refused.getByTestId("trace-row-summary")).toHaveText(
      /^orthologs states 'syntenic', and /,
    );
    await expect
      .poll(async () =>
        (await readNodes(apiClient, id))
          .filter((node) => node.searchName === ORTHOLOGS)
          .map((node) => String(node.parameters?.["isSyntenic"]?.value ?? "")),
      )
      .toEqual(["yes"]);
  });
});
