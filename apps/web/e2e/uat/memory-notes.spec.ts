/**
 * UAT flows M1 to M6: rated answers, the recalled-memories figure, the notes
 * rail, the Memory settings tab and a preference kept across conversations.
 * A test that reads memories starts from an account with none; only the model is mocked.
 */

import type { Browser, BrowserContext, Locator, Page } from "@playwright/test";
import type { MemoryItem, MemoryListResponse } from "@pathfinder/shared";
import type { Note } from "@pathfinder/shared/generated/types/Note";

import { test, expect, BASE_URL } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { type ApiClient, CSRF_HEADERS, clearUserData } from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import {
  expectBuild,
  expectEvidence,
  openTrace,
  traceRows,
} from "../fixtures/build-checks";
import {
  countPattern,
  printed,
  readConversation,
  siteOrganism,
} from "../fixtures/site-reads";
import { wdkTestToken } from "../fixtures/wdk-account";
import { ChatPage } from "../pages/chat.page";
import type { SettingsPage } from "../pages/settings.page";

const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;
const S3_TEXT = (organism: string) =>
  `Find ${organism} genes that have a predicted signal peptide or 2 to 99 transmembrane domains.`;
const N11_TEXT =
  "Please remember for future sessions that I prefer the Su et al. strand-specific dataset for gametocyte expression, then tell me what you stored.";
const M6_QUESTION = "Which dataset do I prefer for gametocyte expression?";
const EDITED_SUMMARY = "UAT edited summary";
const UNMATCHED_WORD = "quokka";
const KIND_BADGE = /^(Gene set|Strategy|Preference|Knowledge|Case)/;
const MEMORY_BUDGET_MS = 60_000;

type MemoryBucket = "strategies" | "preferences" | "cases";

const SECTIONS: [string, MemoryBucket | "geneSetNotes" | "knowledge"][] = [
  ["Gene sets", "geneSetNotes"],
  ["Strategies", "strategies"],
  ["Preferences", "preferences"],
  ["Knowledge", "knowledge"],
  ["Cases", "cases"],
];

function escaped(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Delete every memory and tombstone of the account, as a clean account has none. */
async function startClean(api: ApiClient) {
  const resp = await api.delete("/api/v1/user/data");
  expect(resp.status(), `purge ${await resp.text()}`).toBe(200);
}

async function listMemories(api: ApiClient): Promise<MemoryListResponse> {
  const resp = await api.get("/api/v1/memories?limit=200");
  expect(resp.status()).toBe(200);
  return (await resp.json()) as MemoryListResponse;
}

/** The memory of `bucket` that `match` picks, once the turn wrote it. */
async function memoryWritten(
  api: ApiClient,
  bucket: MemoryBucket,
  match: (item: MemoryItem) => boolean,
): Promise<MemoryItem> {
  let found: MemoryItem | undefined;
  await expect
    .poll(
      async () => {
        found = (await listMemories(api))[bucket].find(match);
        return found?.key ?? "";
      },
      { timeout: MEMORY_BUDGET_MS },
    )
    .not.toBe("");
  if (found === undefined) throw new Error(`no ${bucket} memory was written`);
  return found;
}

/** The preference the remember arc stored: the message, word for word. */
function preferenceStated(api: ApiClient) {
  return memoryWritten(api, "preferences", (item) => item.value.summary === N11_TEXT);
}

/** The memory a conversation wrote into `bucket`. */
function writtenBy(api: ApiClient, bucket: MemoryBucket, conversationId: string) {
  return memoryWritten(
    api,
    bucket,
    (item) => item.value.sourceConversationId === conversationId,
  );
}

/** The tags of the case stored under `key`, or null when none is. */
async function caseTags(api: ApiClient, key: string): Promise<string[] | null> {
  const found = (await listMemories(api)).cases.find((item) => item.key === key);
  return found === undefined ? null : (found.value.tags ?? []);
}

/** Build one arc on a fresh conversation of the project's site. */
async function buildOn(chatPage: ChatPage, siteId: string, message: string) {
  await chatPage.startOn(siteId);
  await chatPage.sendAndSettle(message);
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  return id;
}

/** Click a rating control and wait for the api to store it. */
async function rate(
  page: Page,
  reply: Locator,
  name: "Good response" | "Bad response",
) {
  await reply.hover();
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith("/rating") &&
      ["PUT", "DELETE"].includes(response.request().method()),
  );
  await reply.getByRole("button", { name }).click();
  expect((await saved).ok()).toBe(true);
}

/** The rows of the recalled-memories figure on the thread. */
function recalledRows(page: Page): Locator {
  return page.getByTestId("data-memory-retrieved").getByRole("listitem");
}

/** Open Settings on its Memory tab. */
async function openMemoryTab(page: Page, settingsPage: SettingsPage): Promise<Locator> {
  await settingsPage.open();
  const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
  const tab = dialog.getByRole("tab", { name: "Memory", exact: true });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
  return dialog;
}

/** The header of one kind's section, which reads its title and its count. */
function section(dialog: Locator, title: string): Locator {
  return dialog.getByRole("button", { name: new RegExp(`^${title}\\s*\\d+$`) });
}

/** The listed memory rows that carry `text`. */
function memoryRows(dialog: Locator, text: string): Locator {
  return dialog.getByTestId("memory-row-body").filter({ hasText: text });
}

/** Sign a second PathFinder user in, on the same VEuPathDB login, with no memories. */
async function secondUser(browser: Browser, userId: string): Promise<BrowserContext> {
  const context = await browser.newContext({ baseURL: BASE_URL });
  await context.addCookies([
    { name: "Authorization", value: wdkTestToken(), url: BASE_URL },
  ]);
  const login = await context.request.post(
    `${BASE_URL}/api/v1/dev/login?user_id=${userId}`,
    { headers: CSRF_HEADERS },
  );
  expect(login.ok(), `dev-login ${userId} ${login.status()}`).toBe(true);
  const notice = await context.request.patch(`${BASE_URL}/api/v1/me/privacy`, {
    headers: CSRF_HEADERS,
    data: { noticeSeen: true },
  });
  expect(notice.ok()).toBe(true);
  const purge = await context.request.delete(`${BASE_URL}/api/v1/user/data`, {
    headers: CSRF_HEADERS,
  });
  expect(purge.status()).toBe(200);
  return context;
}

test.describe("Memory and notes", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("M1 - Like an answer", async ({
    chatPage,
    settingsPage,
    apiClient,
    page,
    siteId,
  }) => {
    await startClean(apiClient);
    const message = prompt("intersect", S2_TEXT(siteOrganism(siteId)));
    const first = await buildOn(chatPage, siteId, message);
    const counts = await expectBuild(page, apiClient, first, siteId, LAYOUTS.intersect);
    await expectEvidence(page, "Supported", counts.root);
    const written = await writtenBy(apiClient, "cases", first);

    const reply = chatPage.assistantReply(countPattern(counts.root));
    await expect(reply).toHaveCount(1);
    await expect(
      chatPage.userMessages.getByRole("button", { name: "Good response" }),
    ).toHaveCount(0);
    await rate(page, reply, "Good response");
    await expect(reply.getByRole("button", { name: "Good response" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.reload();
    await expect(reply.getByRole("button", { name: "Good response" })).toHaveAttribute(
      "aria-pressed",
      "true",
      { timeout: 60_000 },
    );
    await expect
      .poll(() => caseTags(apiClient, written.key), { timeout: MEMORY_BUDGET_MS })
      .toContain("pinned");

    const dialog = await openMemoryTab(page, settingsPage);
    await section(dialog, "Cases").click();
    const row = memoryRows(dialog, written.value.name);
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(`reached ${String(counts.root)} results through`);
    await expect(row.getByText("pinned", { exact: true })).toBeVisible();
    await settingsPage.close();

    await chatPage.newChat(siteId);
    await chatPage.sendAndSettle(message);
    const second = chatPage.lastStrategyId ?? "";
    const again = await expectBuild(page, apiClient, second, siteId, LAYOUTS.intersect);
    expect(again.root).toBe(counts.root);
    const recalled = recalledRows(page).filter({ hasText: written.value.name });
    await expect(recalled).toHaveCount(1);
    await expect(recalled).toContainText("Case");

    await page.goto(`/${siteId}/conversation/${first}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    const liked = chatPage.assistantReply(countPattern(counts.root));
    await expect(liked.getByRole("button", { name: "Good response" })).toHaveAttribute(
      "aria-pressed",
      "true",
      { timeout: 60_000 },
    );
    await rate(page, liked, "Good response");
    await expect(liked.getByRole("button", { name: "Good response" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect
      .poll(() => caseTags(apiClient, written.key), { timeout: MEMORY_BUDGET_MS })
      .not.toContain("pinned");
  });

  test("M2 - Dislike an answer", async ({
    chatPage,
    settingsPage,
    apiClient,
    page,
    siteId,
  }) => {
    await startClean(apiClient);
    const message = prompt("union", S3_TEXT(siteOrganism(siteId)));
    const first = await buildOn(chatPage, siteId, message);
    const counts = await expectBuild(page, apiClient, first, siteId, LAYOUTS.union);
    await expectEvidence(page, "Supported", counts.root);
    const written = await writtenBy(apiClient, "cases", first);

    const reply = chatPage.assistantReply(countPattern(counts.root));
    await expect(reply).toHaveCount(1);
    await rate(page, reply, "Bad response");
    await expect(reply.getByRole("button", { name: "Bad response" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.reload();
    await expect(reply.getByRole("button", { name: "Bad response" })).toHaveAttribute(
      "aria-pressed",
      "true",
      { timeout: 60_000 },
    );
    await expect
      .poll(() => caseTags(apiClient, written.key), { timeout: MEMORY_BUDGET_MS })
      .toBeNull();

    const dialog = await openMemoryTab(page, settingsPage);
    const cases = (await listMemories(apiClient)).cases.length;
    await expect(section(dialog, "Cases")).toHaveText(
      new RegExp(`^Cases\\s*${cases}$`),
    );
    await section(dialog, "Cases").click();
    await expect(memoryRows(dialog, written.value.name)).toHaveCount(0);
    await settingsPage.close();

    await chatPage.newChat(siteId);
    await chatPage.sendAndSettle(message);
    await expectBuild(
      page,
      apiClient,
      chatPage.lastStrategyId ?? "",
      siteId,
      LAYOUTS.union,
    );
    await expect(
      recalledRows(page).filter({ hasText: written.value.name }),
    ).toHaveCount(0);
  });

  test("M3 - The recalled-memories figure", async ({
    chatPage,
    settingsPage,
    apiClient,
    page,
    siteId,
  }) => {
    await startClean(apiClient);
    await buildOn(chatPage, siteId, prompt("remember", N11_TEXT));
    const preference = await preferenceStated(apiClient);
    const built = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, built, siteId, LAYOUTS.intersect);
    const strategy = await writtenBy(apiClient, "strategies", built);
    const outcome = await writtenBy(apiClient, "cases", built);
    // Two memories that share one name each show when they were written.
    const renamed = await apiClient.patch(
      `/api/v1/memories/${encodeURIComponent(strategy.key)}?kind=strategy`,
      { data: { name: outcome.value.name } },
    );
    expect(renamed.status()).toBe(200);

    await buildOn(chatPage, siteId, prompt("recall-preference", M6_QUESTION));
    const figure = page.getByTestId("data-memory-retrieved");
    await expect(figure.locator("figcaption")).toHaveText("Recalled memories");
    const rows = figure.getByRole("listitem");
    const shown = await rows.count();
    expect(shown).toBeGreaterThanOrEqual(3);
    await expect(figure.getByTestId("figure-caption")).toHaveText(
      `${printed(shown)} memories`,
    );
    await expect(rows).toHaveText(new Array<RegExp>(shown).fill(KIND_BADGE));
    const preferenceRow = rows.filter({ hasText: preference.value.name });
    await expect(preferenceRow).toHaveCount(1);
    await expect(preferenceRow).toContainText("Preference");
    const shared = rows.filter({ hasText: outcome.value.name });
    await expect(shared).toHaveCount(2);
    await expect(shared.getByTestId("memory-written")).toHaveCount(2);

    const strategyLink = figure.getByRole("link", { name: outcome.value.name });
    await expect(strategyLink).toHaveAttribute("title", outcome.value.name);
    await expect(strategyLink).toHaveAttribute(
      "href",
      `/${siteId}/conversation/${built}`,
    );

    await preferenceRow.getByRole("button", { name: preference.value.name }).click();
    const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("tab", { name: "Memory", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(
      dialog.locator('[data-testid="memory-row-body"][aria-current="true"]'),
    ).toContainText(preference.value.name);
    await settingsPage.close();

    await strategyLink.click();
    await page.waitForURL(new RegExp(`/conversation/${built}$`), { timeout: 60_000 });
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
  });

  test("M4 - Notes in the rail", async ({ chatPage, apiClient, page, siteId }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("intersect", S2_TEXT(siteOrganism(siteId))),
    );
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    const reply = chatPage.assistantReply(countPattern(counts.root));
    await openTrace(reply);
    await expect(traceRows(reply, "Save note")).not.toHaveCount(0);
    await expect(traceRows(reply, "Pin note")).not.toHaveCount(0);

    const listed = await apiClient.get(`/api/v1/conversations/${id}/scratchpad/notes`);
    expect(listed.status()).toBe(200);
    const pinned = ((await listed.json()) as Note[]).filter(
      (note) => note.pinned === true,
    );
    expect(pinned).toHaveLength(1);
    const [note] = pinned;
    if (note === undefined) throw new Error("the build pinned no note");

    await page.getByRole("button", { name: "Open Notes" }).click();
    const panel = page.getByTestId("scratchpad-panel");
    const card = panel.getByTestId(`scratchpad-note-${note.id}`);
    await expect(card).toHaveAttribute("data-pinned", "true");
    await expect(panel.getByText("Pinned", { exact: true })).toBeVisible();
    await expect(card).toContainText(note.title);

    const opener = card.locator("button[aria-expanded]");
    await opener.click();
    await expect(opener).toHaveAttribute("aria-expanded", "true");
    await expect(card.locator("pre")).toHaveText(note.body);

    await card.getByRole("button", { name: "Unpin" }).click();
    await expect(card).toHaveAttribute("data-pinned", "false");
    await expect(panel.getByText("Recent", { exact: true })).toBeVisible();
    await expect(panel.getByText("Pinned", { exact: true })).toHaveCount(0);

    await card.getByRole("button", { name: "Delete note" }).click();
    await expect(card).toHaveCount(0);

    await chatPage.newChat(siteId);
    const openNotes = page.getByRole("button", { name: "Open Notes" });
    if ((await openNotes.count()) > 0) await openNotes.click();
    await expect(page.getByTestId("scratchpad-empty")).toHaveText(
      "No notes yet. The assistant saves findings here as it works.",
    );
  });

  test("M5 - The Memory settings tab: edit, delete, tombstone", async ({
    chatPage,
    settingsPage,
    apiClient,
    page,
    siteId,
  }) => {
    await startClean(apiClient);
    await chatPage.startOn(siteId);
    let dialog = await openMemoryTab(page, settingsPage);
    const search = dialog.getByPlaceholder("Search memories...");
    await search.fill(UNMATCHED_WORD);
    await expect(
      // The product wraps the word in typographic quotes; any one character matches them.
      dialog.getByText(new RegExp(`^No memories matched .${UNMATCHED_WORD}.\\.$`)),
    ).toBeVisible({ timeout: 30_000 });
    await settingsPage.close();

    await buildOn(chatPage, siteId, prompt("remember", N11_TEXT));
    const preference = await preferenceStated(apiClient);
    const message = prompt("intersect", S2_TEXT(siteOrganism(siteId)));
    const built = await buildOn(chatPage, siteId, message);
    await expectBuild(page, apiClient, built, siteId, LAYOUTS.intersect);
    const outcome = await writtenBy(apiClient, "cases", built);

    dialog = await openMemoryTab(page, settingsPage);
    const stored = await listMemories(apiClient);
    for (const [title, bucket] of SECTIONS) {
      const count = stored[bucket].length;
      await expect(section(dialog, title)).toHaveText(
        new RegExp(`^${title}\\s*${String(count)}$`),
      );
      await expect(section(dialog, title)).toHaveAttribute("aria-expanded", "false");
    }

    await dialog.getByPlaceholder("Search memories...").fill("gametocyte");
    const hit = memoryRows(dialog, preference.value.name);
    await expect(hit).toHaveCount(1, { timeout: 30_000 });
    await hit.click();
    const editor = page.getByRole("dialog", { name: "Edit memory" });
    await expect(editor.getByRole("heading", { name: "Edit memory" })).toBeVisible();
    await expect(
      editor.getByRole("textbox", { name: "Name", exact: true }),
    ).toHaveValue(preference.value.name);
    await expect(
      editor.getByRole("textbox", { name: "Summary", exact: true }),
    ).toHaveValue(preference.value.summary);
    await expect(
      editor.getByRole("textbox", { name: "Tags (comma-separated)", exact: true }),
    ).toBeVisible();
    await expect(
      editor.getByRole("textbox", { name: /^Content \(JSON\)/ }),
    ).toBeVisible();
    await expect(
      editor.getByRole("checkbox", { name: "Auto-retrieve in future conversations" }),
    ).toBeVisible();
    await expect(editor.getByRole("button", { name: "Cancel" })).toBeEnabled();
    await editor
      .getByRole("textbox", { name: "Summary", exact: true })
      .fill(EDITED_SUMMARY);
    await editor.getByRole("button", { name: "Save" }).click();
    await expect(editor).toHaveCount(0);
    await expect(hit).toContainText(EDITED_SUMMARY, { timeout: 30_000 });
    const edited = await memoryWritten(
      apiClient,
      "preferences",
      (item) => item.key === preference.key && item.value.summary === EDITED_SUMMARY,
    );
    expect(edited.value.name).toBe(preference.value.name);

    await hit.click();
    await editor.getByRole("textbox", { name: /^Content \(JSON\)/ }).fill("[1]");
    await expect(
      editor.getByText("Invalid JSON - must be an object.", { exact: true }),
    ).toBeVisible();
    await expect(editor.getByRole("button", { name: "Save" })).toBeDisabled();
    await editor.getByRole("button", { name: "Cancel" }).click();
    await expect(editor).toHaveCount(0);

    await dialog.getByPlaceholder("Search memories...").fill("");
    await section(dialog, "Cases").click();
    await expect(memoryRows(dialog, outcome.value.name)).toHaveCount(1);
    const confirmed = new Promise<string>((resolve) => {
      page.once("dialog", (prompted) => {
        resolve(prompted.message());
        void prompted.accept();
      });
    });
    await dialog
      .getByRole("button", { name: `Delete ${outcome.value.name}`, exact: true })
      .click();
    expect(await confirmed).toBe(
      `Delete "${outcome.value.name}"? PathFinder will not save it again on its own.`,
    );
    await expect(memoryRows(dialog, outcome.value.name)).toHaveCount(0);
    await expect.poll(() => caseTags(apiClient, outcome.key)).toBeNull();
    const casesLeft = (await listMemories(apiClient)).cases.length;
    await settingsPage.close();

    await buildOn(chatPage, siteId, prompt("recall-preference", M6_QUESTION));
    await expect(
      chatPage.assistantReply(new RegExp(escaped(EDITED_SUMMARY))),
    ).not.toHaveCount(0);

    const rerun = await buildOn(chatPage, siteId, message);
    const counts = await expectBuild(page, apiClient, rerun, siteId, LAYOUTS.intersect);
    await expectEvidence(page, "Supported", counts.root);
    expect(await caseTags(apiClient, outcome.key)).toBeNull();
    expect((await listMemories(apiClient)).cases).toHaveLength(casesLeft);
  });

  test("M6 - A preference remembered across conversations", async ({
    browser,
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    await startClean(apiClient);
    await buildOn(chatPage, siteId, prompt("remember", N11_TEXT));
    const preference = await preferenceStated(apiClient);

    const asked = await buildOn(
      chatPage,
      siteId,
      prompt("recall-preference", M6_QUESTION),
    );
    const row = recalledRows(page).filter({ hasText: preference.value.name });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("Preference");
    const stated = new RegExp(escaped(preference.value.summary));
    await expect(chatPage.assistantReply(stated)).not.toHaveCount(0);
    await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
    expect((await readConversation(apiClient, asked)).steps ?? []).toEqual([]);

    const other = await secondUser(
      browser,
      `uat-m6-b-${String(test.info().workerIndex)}`,
    );
    try {
      const otherPage = await other.newPage();
      const otherChat = new ChatPage(otherPage);
      await otherChat.startOn(siteId);
      await otherChat.sendAndSettle(prompt("recall-preference", M6_QUESTION));
      await expect(otherPage.getByTestId("data-memory-retrieved")).toHaveCount(0);
      await expect(otherChat.assistantReply(stated)).toHaveCount(0);
      await expect(otherChat.assistantMessages).not.toHaveCount(0);
      await clearUserData(other.request, BASE_URL);
    } finally {
      await other.close();
    }
  });
});
