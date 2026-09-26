/**
 * UAT flows F1 to F12 (first run and navigation) and R2, R6 (resilience).
 * Counts, names and ids are read from the site and the api at run time; only
 * the model is mocked.
 */

import {
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
  request,
} from "@playwright/test";
import {
  type AuthStatusResponse,
  type GeneSet,
  type MemoryItem,
  type MemoryListResponse,
  type SiteResponse,
  siteShortName,
} from "@pathfinder/shared";
import type { QuotaResponse } from "@pathfinder/shared/generated/types/QuotaResponse";
import type { ReadinessResponse } from "@pathfinder/shared/generated/types/ReadinessResponse";
import type { TaskListResponse } from "@pathfinder/shared/generated/types/TaskListResponse";
import type { WdkStrategyListItem } from "@pathfinder/shared/generated/types/WdkStrategyListItem";
import * as fs from "node:fs";
import * as path from "node:path";

import { BASE_URL, test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import {
  type ApiClient,
  CSRF_HEADERS,
  fetchConversationMessages,
  fetchStoppedTurnCount,
  fetchUserMessageIds,
  listBody,
  listConversations,
} from "../fixtures/api-client";
import type { AstNode } from "../fixtures/ast";
import { LAYOUTS, TRANSMEMBRANE, layoutOf } from "../fixtures/arc-layouts";
import {
  expectBuild,
  openTrace,
  strategyFigure,
  traceRows,
} from "../fixtures/build-checks";
import { entrySiteId } from "../fixtures/entry-site";
import {
  countPattern,
  printed,
  readConversation,
  readNodes,
  siteControlSets,
  siteCounts,
  siteOrganism,
  storedNodes,
  strategyCaption,
} from "../fixtures/site-reads";
import { signInAsWdkAccount, wdkTestToken } from "../fixtures/wdk-account";
import { ChatPage } from "../pages/chat.page";
import type { GraphPage } from "../pages/graph.page";
import { openConversationId } from "../pages/navigation";
import { SidebarPage } from "../pages/sidebar.page";

const S1_TEXT = (organism: string) =>
  `Find ${organism} genes whose proteins have a predicted signal peptide.`;
const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;
const S4_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide, excluding any gene with 2 to 99 transmembrane domains.`;
const EDIT_TEXT = "Change the transmembrane range to 1 to 99.";
const COUNT_QUESTION = "How many genes does this strategy return?";

/** The refusal the api answers a sign-in the site does not accept with. */
const REFUSED_SIGN_IN = "Invalid email or password";
const REVERT_TEXT =
  "Delete every message after this point in this conversation. Notes and pending " +
  "tasks from those turns are also removed. The strategy goes back to what it was " +
  "at this message; a later version stays in your VEuPathDB account. Saved gene " +
  "sets are kept.";
const CONTROL_TESTS = "Run control tests";
const CONTROL_TESTS_TOOL = "run_control_tests_on_step";
/** A sidebar time for today, as `toLocaleTimeString` prints it in en-US. */
const TODAY_TIME = String.raw`\d{1,2}:\d{2}\s[AP]M`;
const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The reply that carries the `Strategy updated` figure of `steps` and `genes`. */
function captionPattern(steps: number, genes: number): RegExp {
  return new RegExp(escapeRegExp(strategyCaption(steps, genes)));
}

/** The one node running `searchName`. */
function nodeBySearch(nodes: readonly AstNode[], searchName: string): AstNode {
  const matches = nodes.filter((node) => node.searchName === searchName);
  expect(matches, `exactly one ${searchName} step`).toHaveLength(1);
  return matches[0] as AstNode;
}

/** A parameter's value as text, single or multi pick. */
function paramText(node: AstNode, name: string): string {
  const param = node.parameters?.[name];
  if (param === undefined) return "";
  if (param.values !== undefined) return param.values.map(String).join(",");
  return String(param.value ?? "");
}

/** Every leaf's parameter set, keyed by its search. */
function leafParameters(nodes: readonly AstNode[]): Record<string, unknown> {
  return Object.fromEntries(
    nodes
      .filter((node) => node.parameters != null && node.searchName != null)
      .map((node) => [node.searchName ?? "", node.parameters]),
  );
}

/** Build one arc on a fresh conversation of the project's site. */
async function buildOn(
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

/** Open the canvas and wait for its topbar to settle. */
async function openCanvas(
  graphPage: GraphPage,
  siteId: string,
  conversationId: string,
) {
  await graphPage.goToStrategy(siteId, conversationId);
  await graphPage.expectStrategyTopbar();
  await expect(graphPage.strategyPageSyncState).toHaveAttribute(
    "data-sync-state",
    "idle",
    { timeout: 30_000 },
  );
}

/** A new, empty conversation on `siteId`, named `name`. */
async function namedConversation(
  api: ApiClient,
  siteId: string,
  name: string,
): Promise<string> {
  const opened = await api.post("/api/v1/conversations/open", { data: { siteId } });
  expect(opened.status(), `open ${await opened.text()}`).toBe(200);
  const { conversationId } = (await opened.json()) as { conversationId: string };
  await renamed(api, conversationId, name);
  return conversationId;
}

async function renamed(api: ApiClient, conversationId: string, name: string) {
  const resp = await api.patch(`/api/v1/conversations/${conversationId}`, {
    data: { name },
  });
  expect(resp.status(), `rename ${await resp.text()}`).toBe(200);
}

/** The ids of the strategies the VEuPathDB account holds on `siteId`. */
async function accountStrategyIds(api: ApiClient, siteId: string): Promise<number[]> {
  const url = `/api/v1/sites/${siteId}/strategies`;
  const rows = await listBody<WdkStrategyListItem>(await api.get(url), url);
  return rows.map((row) => row.wdkStrategyId);
}

/** The statuses of the conversation's control-test tasks. */
async function controlTaskStatuses(api: ApiClient, conversationId: string) {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/tasks`);
  expect(resp.status()).toBe(200);
  const { tasks } = (await resp.json()) as TaskListResponse;
  return tasks
    .filter((task) => task.toolName === CONTROL_TESTS_TOOL)
    .map((task) => task.status);
}

/** Every memory the caller holds, of every kind. */
async function memoryItems(api: ApiClient): Promise<MemoryItem[]> {
  const resp = await api.get("/api/v1/memories");
  expect(resp.status()).toBe(200);
  const list = (await resp.json()) as MemoryListResponse;
  return [
    ...list.geneSetNotes,
    ...list.strategies,
    ...list.preferences,
    ...list.knowledge,
    ...list.cases,
  ];
}

/** The suggestion prompts the empty thread offers on `siteId`. */
function suggestionsFor(siteId: string): string[] {
  const file = path.resolve("src/features/conversation/data/suggestedQuestions.json");
  const bank = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, string[]>;
  return bank[siteId] ?? [];
}

/** The ids of the sidebar rows, top to bottom. */
function rowIds(page: Page): Promise<string[]> {
  return page
    .getByTestId("conversation-item")
    .evaluateAll((rows) =>
      rows.map((row) => row.getAttribute("data-conversation-id") ?? ""),
    );
}

/** Open a sidebar row's `Conversation actions` menu. */
async function openRowMenu(row: Locator) {
  await row.hover();
  await row.getByRole("button", { name: "Conversation actions" }).click();
}

/**
 * A browser context signed in as its own PathFinder user with the registered
 * VEuPathDB token, the way the worker fixture signs a worker in.
 */
async function signedInUser(
  browser: Browser,
  userId: string,
  acknowledgeNotice: boolean,
): Promise<BrowserContext> {
  const context = await browser.newContext({
    storageState: { cookies: [], origins: [] },
  });
  await context.addCookies([
    { name: "Authorization", value: wdkTestToken(), url: BASE_URL },
  ]);
  const login = await context.request.post(
    `${BASE_URL}/api/v1/dev/login?user_id=${userId}`,
    { headers: CSRF_HEADERS },
  );
  expect(login.ok(), `dev login ${login.status()}`).toBe(true);
  if (acknowledgeNotice) {
    const notice = await context.request.patch(`${BASE_URL}/api/v1/me/privacy`, {
      headers: CSRF_HEADERS,
      data: { noticeSeen: true },
    });
    expect(notice.ok(), `privacy notice ${notice.status()}`).toBe(true);
  }
  return context;
}

/** The sign-in dialog's email, password and button, filled and pressed. */
async function submitSignIn(dialog: Locator, email: string, password: string) {
  await dialog.getByPlaceholder("Email").fill(email);
  await dialog.getByPlaceholder("Password").fill(password);
  await dialog.getByRole("button", { name: "Sign in", exact: true }).click();
}

/** Run one slash command whose first step is a text or select parameter. */
async function openSlash(page: Page, chatPage: ChatPage, command: string) {
  await chatPage.messageInput.fill(command);
  await expect(page.getByTestId("slash-popover")).toBeVisible();
  await chatPage.messageInput.press("Enter");
}

test.describe("First run and navigation", () => {
  test("F1 - Sign in", async ({ browser, siteId }) => {
    test.setTimeout(300_000);
    const email = process.env["WDK_TEST_EMAIL"] ?? "";
    const password = process.env["WDK_TEST_PASSWORD"] ?? "";
    // The account acknowledges its learning notice first, so only the sign-in dialog shows.
    const account = await request.newContext({
      baseURL: BASE_URL,
      extraHTTPHeaders: CSRF_HEADERS,
    });
    await signInAsWdkAccount(account, siteId);
    await account.dispose();

    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
    });
    const page = await context.newPage();
    const entry = await entrySiteId(context, BASE_URL);
    await page.goto(`${BASE_URL}/${entry}/conversation`);

    const dialog = page.getByRole("dialog", { name: "Sign in to VEuPathDB" });
    await expect(dialog).toBeVisible({ timeout: 30_000 });
    await expect(dialog).toContainText("PathFinder");
    await expect(dialog).toContainText("VEuPathDB Strategy Builder");
    await expect(dialog).toContainText(
      "Sign in with your VEuPathDB account to build and manage search strategies.",
    );
    await expect(dialog.getByPlaceholder("Email")).toBeVisible();
    await expect(dialog.getByPlaceholder("Password")).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
    await expect(dialog).toContainText("We do not store your login credentials.");
    await expect(dialog.getByRole("button", { name: "Close" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId("message-composer")).toHaveCount(0);

    await submitSignIn(
      dialog,
      `uat-f1-${Date.now()}@example.invalid`,
      "not-the-password",
    );
    await expect(dialog.getByText(REFUSED_SIGN_IN)).toBeVisible({ timeout: 60_000 });
    await expect(dialog).toBeVisible();

    await submitSignIn(dialog, email, password);
    await expect(dialog.getByRole("button", { name: "Signing in..." })).toBeVisible();
    await expect(dialog).toHaveCount(0, { timeout: 60_000 });
    await expect(page).toHaveURL(new RegExp(`/${entry}/conversation$`));
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });

    const fresh = await signedInUser(browser, `uat-f1-${Date.now()}`, false);
    const freshPage = await fresh.newPage();
    await freshPage.goto(`${BASE_URL}/${siteId}/conversation`);
    const notice = freshPage.getByRole("dialog", { name: "How PathFinder learns" });
    await expect(notice).toBeVisible({ timeout: 60_000 });
    await expect(notice.getByRole("button", { name: "Turn off" })).toBeVisible();
    await notice.getByRole("button", { name: "OK", exact: true }).click();
    await expect(notice).toHaveCount(0);
    const privacy = await fresh.request.get(`${BASE_URL}/api/v1/me/privacy`);
    expect(((await privacy.json()) as { noticeSeen: boolean }).noticeSeen).toBe(true);
    await freshPage.reload();
    await expect(freshPage.getByTestId("message-composer")).toBeVisible({
      timeout: 60_000,
    });
    await expect(notice).toHaveCount(0);
    await fresh.close();

    const statusResp = await context.request.get(
      `${BASE_URL}/api/v1/veupathdb/auth/status?siteId=${entry}`,
    );
    const status = (await statusResp.json()) as AuthStatusResponse;
    const shownName = status.name != null && status.name !== "" ? status.name : "-";
    await expect(
      page.getByText(`Logged in as ${shownName}`, { exact: true }),
    ).toBeVisible();
    const quota = (await (
      await context.request.get(`${BASE_URL}/api/v1/me/quota`)
    ).json()) as QuotaResponse;
    const pill = page.getByLabel("Monthly quota");
    await expect(pill).toHaveText(
      new RegExp(`^\\$[\\d,.]+ / ${escapeRegExp(USD.format(Number(quota.limitUsd)))}$`),
    );
    await pill.hover();
    await expect(page.getByRole("tooltip")).toContainText(
      "Account total this month, across all conversations.",
    );

    const before = (await listConversations(context.request, entry)).map(
      (row) => row.id,
    );
    await page.getByRole("button", { name: "Log out", exact: true }).click();
    await expect(dialog).toBeVisible({ timeout: 30_000 });
    await submitSignIn(dialog, email, password);
    await expect(dialog).toHaveCount(0, { timeout: 60_000 });
    const after = (await listConversations(context.request, entry)).map(
      (row) => row.id,
    );
    expect(after.sort()).toEqual(before.sort());

    await context.close();
  });

  test("F3 - A site that is down", async ({ page, apiClient, siteId }) => {
    const ready = await apiClient.get("/health/ready");
    expect(ready.status()).toBe(200);
    const readiness = (await ready.json()) as ReadinessResponse;
    expect(readiness.status).toBe("healthy");
    expect(readiness.notReady ?? []).toEqual([]);

    const sitesResp = await apiClient.get("/api/v1/sites");
    expect(sitesResp.status()).toBe(200);
    const rows = (await sitesResp.json()) as SiteResponse[];
    // A site is unavailable exactly when it carries a reason.
    for (const row of rows) expect(row.available).toBe(row.unavailableReason == null);
    const ids = rows.map((row) => row.id);
    for (const degraded of readiness.degraded ?? []) expect(ids).toContain(degraded);

    await page.goto("/");
    await page.waitForURL(/\/[^/]+\/conversation/, { timeout: 60_000 });
    const landedOn = new URL(page.url()).pathname.split("/")[1] ?? "";
    expect(rows.filter((row) => row.available).map((row) => row.id)).toContain(
      landedOn,
    );

    const down = siteId === "toxodb" ? "plasmodb" : "toxodb";
    const downRow = rows.find((row) => row.id === down);
    if (downRow === undefined) throw new Error(`the api lists no site ${down}`);
    const reason = "the site did not answer in time";
    await page.route(
      (url) => url.pathname === "/api/v1/sites",
      async (route) => {
        const response = await route.fetch();
        const listed = (await response.json()) as SiteResponse[];
        await route.fulfill({
          response,
          json: listed.map((row) =>
            row.id === down
              ? { ...row, available: false, unavailableReason: reason }
              : row,
          ),
        });
      },
    );
    await page.goto(`/${siteId}/conversation`);
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });

    const switcher = page.getByRole("button", { name: "Switch site" });
    await switcher.click();
    const item = page.getByTestId(`site-menu-item-${down}`);
    await expect(item).toHaveAttribute(
      "aria-label",
      `Couldn't reach ${downRow.displayName}`,
    );
    await expect(page.getByTestId(`site-degraded-${down}`)).toHaveText(
      "Couldn't reach",
    );
    await item.click();
    await expect(page).toHaveURL(new RegExp(`/${down}/conversation$`), {
      timeout: 60_000,
    });

    const notice = page.getByTestId("site-unavailable-notice");
    await expect(notice).toContainText(`Couldn't reach ${siteShortName(down)}`);
    await expect(notice).toContainText(
      `PathFinder cannot use this site right now: ${reason}. It keeps trying every minute, so this may clear on its own.`,
    );
    await expect(notice).toContainText("Try another site:");
    const alternatives = rows.filter((row) => row.available && row.id !== down);
    await expect(notice.getByRole("link")).toHaveCount(alternatives.length);
    for (const row of alternatives) {
      await expect(
        notice.getByRole("link", { name: row.displayName, exact: true }),
      ).toBeVisible();
    }
    await expect(switcher).toBeVisible();
    await expect(page.getByTestId("conversations-new-button")).toBeVisible();
    await expect(page.getByText(/^Logged in as /)).toBeVisible();
    await expect(page.getByTestId("site-trigger-degraded")).toHaveAttribute(
      "aria-label",
      `Couldn't reach ${siteShortName(down)}`,
    );
    await switcher.hover();
    await expect(page.getByRole("tooltip")).toContainText(
      `Couldn't reach ${siteShortName(down)}`,
    );
  });

  test("F5 - New conversation and the assistant menu", async ({
    page,
    chatPage,
    sidebarPage,
    settingsPage,
    apiClient,
    siteId,
  }) => {
    await page.goto(`/${siteId}/conversation`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await sidebarPage.createNew();
    await expect(page).toHaveURL(new RegExp(`/${siteId}/conversation$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      /^(Good morning|Good afternoon|Good evening|Still up\?)$/,
    );
    const blurb = page.getByTestId("chat-empty-blurb");
    await expect(blurb).toHaveText(
      `Build and refine multi-step ${siteShortName(siteId)} search strategies with guided parameter selection and validation.`,
    );
    const suggestions = suggestionsFor(siteId);
    expect(suggestions).toHaveLength(4);
    for (const suggestion of suggestions) {
      await expect(
        page.getByRole("button", { name: suggestion, exact: true }),
      ).toBeVisible();
    }

    const builderText = "hello strategy builder";
    await chatPage.sendTurn(builderText, /\[mock\] hello strategy builder/);
    const builderId = await openConversationId(page);
    expect((await readConversation(apiClient, builderId)).assistantId).toBe(
      "pathfinder",
    );

    await page.getByTestId("conversations-new-assistant-button").click();
    const menu = page.getByRole("menu");
    await expect(menu).toContainText("New conversation with");
    await expect(page.getByTestId("new-chat-assistant-pathfinder")).toHaveText(
      "Strategy builder",
    );
    await expect(page.getByTestId("new-chat-assistant-site_help")).toHaveText(
      "Site help",
    );
    await expect(page.getByTestId("open-wdk-strategy-menu-item")).toHaveText(
      "Open a VEuPathDB strategy...",
    );
    await page.getByTestId("new-chat-assistant-site_help").click();
    await page.waitForURL(
      (url) =>
        url.pathname === `/${siteId}/conversation` &&
        url.searchParams.get("assistant") === "site_help",
      { timeout: 60_000 },
    );
    await expect(page.getByTestId("chat-assistant-label")).toHaveText("Site help");
    await expect(blurb).toHaveText(
      "Find your way around the VEuPathDB sites: which site covers an organism, and what each one lets you search.",
    );
    for (const suggestion of suggestions) {
      await expect(
        page.getByRole("button", { name: suggestion, exact: true }),
      ).toHaveCount(0);
    }

    const question = "Which site holds Aedes aegypti?";
    await chatPage.sendTurn(
      question,
      new RegExp(`\\[mock\\] ${escapeRegExp(question)}`),
    );
    const helpId = await openConversationId(page);
    expect((await readConversation(apiClient, helpId)).assistantId).toBe("site_help");
    await chatPage.refreshConversationsButton.click();
    await expect(sidebarPage.item(helpId)).toContainText(
      new RegExp(`Site help · ${TODAY_TIME}`),
      { timeout: 30_000 },
    );

    await settingsPage.open();
    await settingsPage.openTab("Model");
    const settings = page.getByRole("dialog", { name: "Settings", exact: true });
    await expect(settings).toContainText(
      "Site help runs each stage below on its own model.",
    );
    await expect(settings.locator('[data-testid^="phase-row-"]')).toHaveCount(1);
    await expect(settings.getByTestId("phase-row-site_help")).toContainText(
      "Site help",
    );
    await settingsPage.close();
  });
});

test.describe("Site menu", { tag: "@named-site" }, () => {
  test("F2 - Site menu", async ({
    page,
    sitePicker,
    sidebarPage,
    apiClient,
    siteId,
  }) => {
    const other = siteId === "toxodb" ? "plasmodb" : "toxodb";
    const home = await namedConversation(apiClient, siteId, "UAT F2 home");
    const away = await namedConversation(apiClient, other, "UAT F2 away");
    const sitesResp = await apiClient.get("/api/v1/sites");
    expect(sitesResp.status()).toBe(200);
    const rows = (await sitesResp.json()) as SiteResponse[];

    await page.goto(`/${siteId}/conversation`);
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });
    await sidebarPage.refresh();
    await expect(sidebarPage.item(home)).toBeVisible({ timeout: 30_000 });

    const switcher = page.getByRole("button", { name: "Switch site" });
    await switcher.hover();
    await expect(page.getByRole("tooltip")).toContainText("Switch site");
    await switcher.click();
    const menu = page.getByRole("menu");
    await expect(menu.getByText("Component sites", { exact: true })).toBeVisible();
    await expect(menu.getByText("Portal", { exact: true })).toBeVisible();
    for (const row of rows) {
      await expect(page.getByTestId(`site-menu-item-${row.id}`)).toContainText(
        row.displayName,
      );
    }
    await expect(menu.locator('[data-testid^="site-degraded-"]')).toHaveCount(0);
    await page.keyboard.press("Escape");

    const banner = page.locator("header").filter({ hasText: "PathFinder" });
    await expect(banner).toHaveAttribute(
      "style",
      new RegExp(`/banners/${siteId}\\.jpg`),
    );
    await sitePicker.selectSite(other);
    await expect(page).toHaveURL(new RegExp(`/${other}/conversation$`));
    await expect(banner).toHaveAttribute(
      "style",
      new RegExp(`/banners/${other}\\.jpg`),
    );
    await expect(sidebarPage.item(away)).toBeVisible({ timeout: 30_000 });
    await expect(sidebarPage.item(home)).toHaveCount(0);

    await sitePicker.selectSite(siteId);
    await expect(sidebarPage.item(home)).toBeVisible({ timeout: 30_000 });
    await expect(sidebarPage.item(away)).toHaveCount(0);
  });
});

test.describe("First run and navigation with the model", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("F4 - The conversation list", async ({
    chatPage,
    sidebarPage,
    apiClient,
    page,
    siteId,
  }) => {
    const built = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, built, siteId, LAYOUTS.single);
    await renamed(apiClient, built, "UAT F4 alpha");
    const empty = await namedConversation(apiClient, siteId, "UAT F4 beta");

    await sidebarPage.refresh();
    await expect(page.getByText("Conversations", { exact: true })).toBeVisible();
    await expect(sidebarPage.item(built)).toContainText("UAT F4 alpha", {
      timeout: 30_000,
    });
    await expect(sidebarPage.item(built)).toContainText(
      new RegExp(`UAT F4 alpha${LAYOUTS.single.steps} step · ${TODAY_TIME}`),
    );
    await expect(sidebarPage.item(empty)).toContainText(
      new RegExp(`UAT F4 beta${TODAY_TIME}`),
    );
    await expect.poll(() => rowIds(page)).toEqual([empty, built]);

    await sidebarPage.search("al");
    await expect(sidebarPage.items).toHaveCount(1);
    await expect(sidebarPage.item(built)).toBeVisible();
    await sidebarPage.search("zq");
    await expect(sidebarPage.items).toHaveCount(0);
    await expect(page.getByText("No conversations match your search.")).toBeVisible();
    await sidebarPage.clearSearch();

    await renamed(apiClient, built, "UAT F4 alpha again");
    await sidebarPage.refresh();
    await expect(sidebarPage.item(built)).toContainText("UAT F4 alpha again");
    await expect.poll(() => rowIds(page)).toEqual([built, empty]);
  });

  test("F6 - Rename", async ({
    chatPage,
    sidebarPage,
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
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

    const row = sidebarPage.item(id);
    const title = (await row.locator("div[title]").getAttribute("title")) ?? "";
    await openRowMenu(row);
    await page.getByRole("menuitem", { name: "Rename" }).click();
    const input = page.getByTestId("conversation-rename-input");
    await expect(input).toHaveValue(title);
    await input.fill("UAT rename F6");
    await input.press("Enter");
    await expect(row).toContainText("UAT rename F6");
    await expect
      .poll(async () => (await readConversation(apiClient, id)).name)
      .toBe("UAT rename F6");
    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await expect(sidebarPage.item(id)).toContainText("UAT rename F6");

    const stepper = page.getByTestId("slash-param-stepper");
    await openSlash(page, chatPage, "/rename");
    await page.getByTestId("slash-param-text-name").fill("UAT rename F6 slash");
    await stepper.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText('Renamed to "UAT rename F6 slash".')).toBeVisible();
    await expect(sidebarPage.item(id)).toContainText("UAT rename F6 slash");

    await openSlash(page, chatPage, "/rename");
    await expect(page.getByTestId("slash-param-text-name")).toHaveValue("");
    await stepper.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText("Name cannot be empty.")).toBeVisible();

    const strategyName = "UAT signal peptide screen";
    await chatPage.sendAndSettle(
      prompt("rename", `Rename this strategy to ${strategyName}.`),
    );
    const reply = chatPage.assistantMessages.filter({
      has: page.getByTestId("trace-row").filter({ hasText: "Rename strategy" }),
    });
    await expect(reply).toHaveCount(1);
    await openTrace(reply);
    await expect(traceRows(reply, "Rename strategy")).not.toHaveCount(0);
    await expect
      .poll(async () => (await readConversation(apiClient, id)).name)
      .toBe(strategyName);
    await expect(sidebarPage.item(id)).toContainText(strategyName);
    await openCanvas(graphPage, siteId, id);
    await expect(graphPage.strategyPageNameInput).toHaveValue(strategyName);
  });

  test("F7 - Delete, dismiss and restore", async ({
    chatPage,
    sidebarPage,
    apiClient,
    page,
    siteId,
  }) => {
    const message = prompt("single", S1_TEXT(siteOrganism(siteId)));
    const id = await buildOn(chatPage, siteId, message);
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    const wdkStrategyId = (await readConversation(apiClient, id)).wdkStrategyId ?? 0;
    expect(wdkStrategyId).toBeGreaterThan(0);
    const site = siteShortName(siteId);

    const row = sidebarPage.item(id);
    const title = (await row.locator("div[title]").getAttribute("title")) ?? "";
    await openRowMenu(row);
    await page.getByRole("menuitem", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog", { name: "Delete conversation" });
    await expect(dialog).toContainText(
      `Delete "${title}"? It moves to Recently deleted and can be restored later.`,
    );
    await expect(dialog).toContainText(`Also delete strategy from ${site}`);
    await expect(dialog.getByRole("checkbox")).not.toBeChecked();
    await expect(dialog.getByTestId("delete-linked-strategy-note")).toHaveText(
      `PathFinder created this strategy in ${site}. Deleting it is permanent, and the conversation will not be recoverable.`,
    );
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(row).toHaveCount(0, { timeout: 15_000 });
    await sidebarPage.expectDismissedCount(1);
    expect(await accountStrategyIds(apiClient, siteId)).toContain(wdkStrategyId);

    await sidebarPage.expandDismissed();
    await sidebarPage.restoreDismissed(id);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await sidebarPage.selectConversation(id);
    await expect(chatPage.userMessage(message)).toHaveCount(1, { timeout: 30_000 });

    await openRowMenu(row);
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(row).toHaveCount(0, { timeout: 15_000 });
    await sidebarPage.expectNoDismissedSection();
    const dismissed = await listConversations(apiClient, siteId, "dismissed");
    expect(dismissed.map((d) => d.id)).not.toContain(id);
    await expect
      .poll(() => accountStrategyIds(apiClient, siteId), { timeout: 30_000 })
      .not.toContain(wdkStrategyId);
  });

  test("F8 - Branch", async ({ chatPage, sidebarPage, apiClient, page, siteId }) => {
    const buildText = prompt("minus", S4_TEXT(siteOrganism(siteId)));
    const editText = prompt("edit-param", EDIT_TEXT);
    const parentId = await buildOn(chatPage, siteId, buildText);
    const first = await expectBuild(page, apiClient, parentId, siteId, LAYOUTS.minus);
    const firstLeaves = leafParameters(await readNodes(apiClient, parentId));
    await chatPage.sendAndSettle(editText);
    await expect
      .poll(async () => leafParameters(await readNodes(apiClient, parentId)))
      .not.toEqual(firstLeaves);
    const edited = await expectBuild(page, apiClient, parentId, siteId, LAYOUTS.minus);
    expect(edited.root).not.toBe(first.root);
    const parent = await readConversation(apiClient, parentId);

    const branchId = await chatPage.branchFromAssistantReply(
      captionPattern(LAYOUTS.minus.steps, first.root),
    );
    expect(branchId).not.toBe(parentId);
    await expect(chatPage.userMessage(buildText)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessages).toHaveCount(1);
    await expect(chatPage.assistantMessages).toHaveCount(1);
    const branchLog = await fetchConversationMessages(apiClient, branchId);
    expect(branchLog.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(branchLog[0]?.content).toBe(buildText);
    const parentLog = await fetchConversationMessages(apiClient, parentId);
    expect(parentLog.map((m) => m.role)).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
    ]);

    await sidebarPage.refresh();
    const branchRow = page.locator(
      `[data-testid="subtree-item"][data-conversation-id="${branchId}"]`,
    );
    await expect(branchRow).toBeVisible({ timeout: 15_000 });
    const branch = await readConversation(apiClient, branchId);
    expect(branch.parentConversationId).toBe(parentId);
    expect(branch.wdkStrategyId ?? 0).toBeGreaterThan(0);
    expect(branch.wdkStrategyId).not.toBe(parent.wdkStrategyId);
    const atBranch = await expectBuild(
      page,
      apiClient,
      branchId,
      siteId,
      LAYOUTS.minus,
    );
    expect(atBranch.root).toBe(first.root);
    expect(leafParameters(await readNodes(apiClient, branchId))).toEqual(firstLeaves);

    await chatPage.sendAndSettle(prompt("recap", COUNT_QUESTION));
    const recap = chatPage.assistantMessages.filter({
      hasNot: page.getByTestId("data-graph-snapshot"),
    });
    await expect(recap).toHaveCount(1);
    await expect(recap).toContainText(countPattern(first.root));
    await expect(recap).not.toContainText(countPattern(edited.root));
    await expect(recap.getByTestId("data-sub-agent-call")).toHaveCount(0);

    await page.goto(`/${siteId}/conversation/${parentId}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await expect(chatPage.userMessages).toHaveCount(2, { timeout: 30_000 });
    await expect(chatPage.userMessage(editText)).toHaveCount(1);
    await expect(
      strategyFigure(page, LAYOUTS.minus.steps, edited.root),
    ).not.toHaveCount(0);
    expect((await siteCounts(apiClient, parentId, siteId)).root).toBe(edited.root);

    await branchRow.hover();
    await branchRow.getByRole("button", { name: "Branch actions" }).click();
    await page.getByRole("menuitem", { name: "Delete branch" }).click();
    const dialog = page.getByRole("dialog", { name: "Delete conversation" });
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(branchRow).toHaveCount(0, { timeout: 15_000 });
    await expect
      .poll(() => accountStrategyIds(apiClient, siteId), { timeout: 30_000 })
      .not.toContain(branch.wdkStrategyId);
  });

  test("F9 - Revert", async ({ chatPage, apiClient, page, siteId }) => {
    const buildText = prompt("minus", S4_TEXT(siteOrganism(siteId)));
    const editText = prompt("edit-param", EDIT_TEXT);
    const id = await buildOn(chatPage, siteId, buildText);
    const first = await expectBuild(page, apiClient, id, siteId, LAYOUTS.minus);
    const firstLeaves = leafParameters(await readNodes(apiClient, id));
    await chatPage.sendAndSettle(editText);
    await expect
      .poll(async () => leafParameters(await readNodes(apiClient, id)))
      .not.toEqual(firstLeaves);

    await chatPage.openEditDialog(buildText, buildText);
    const dialog = page.getByRole("dialog", { name: "Edit earlier message" });
    await expect(dialog).toContainText("Branch to a new conversation");
    await expect(dialog).toContainText("Revert this conversation");
    await expect(dialog).toContainText(REVERT_TEXT);
    const revert = await chatPage.confirmRevert();
    expect(revert.status()).toBe(204);

    await expect(chatPage.userMessage(editText)).toHaveCount(0, { timeout: 30_000 });
    await expect(chatPage.userMessage(buildText)).toHaveCount(1);
    await expect(chatPage.editDialogError).toHaveCount(0);
    await chatPage.awaitTurn(captionPattern(LAYOUTS.minus.steps, first.root));
    const rebuilt = await expectBuild(page, apiClient, id, siteId, LAYOUTS.minus);
    expect(rebuilt.root).toBe(first.root);
    expect(leafParameters(await readNodes(apiClient, id))).toEqual(firstLeaves);

    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await expect(chatPage.userMessage(buildText)).toHaveCount(1, { timeout: 30_000 });
    await expect(chatPage.userMessage(editText)).toHaveCount(0);
    expect(await fetchUserMessageIds(apiClient, id)).toHaveLength(1);
  });

  test("F10 - Reload and Stop in the middle of a turn", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const buildText = prompt("intersect", S2_TEXT(siteOrganism(siteId)));
    const status = page.getByTestId("assistant-status");

    await chatPage.startOn(siteId);
    const reloadedId = chatPage.lastStrategyId ?? "";
    await chatPage.send(buildText);
    await expect(status).toHaveText(/Planning/, { timeout: 60_000 });
    await page.reload();
    await expect(page).toHaveURL(new RegExp(`/conversation/${reloadedId}$`));
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/reconnecting/i)).toHaveCount(0);
    await chatPage.expectIdle(240_000);
    const counts = await expectBuild(
      page,
      apiClient,
      reloadedId,
      siteId,
      LAYOUTS.intersect,
    );
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);
    await expect(page.getByText(/reconnecting/i)).toHaveCount(0);

    await chatPage.newChat(siteId);
    const stoppedId = chatPage.lastStrategyId;
    const cancelRequest = page.waitForRequest(
      (r) =>
        r.method() === "POST" &&
        /\/api\/v1\/conversations\/[^/]+\/cancel$/.test(r.url()),
      { timeout: 60_000 },
    );
    await chatPage.send(buildText);
    // The composer ignores a Stop inside the double-click guard window of Send.
    await expect(status).toHaveText(/Planning/, { timeout: 60_000 });
    await chatPage.stopStreaming();
    const cancelled = await (await cancelRequest).response();
    expect(cancelled?.status()).toBe(204);
    await chatPage.expectIdle();
    const stopped = chatPage.assistantMessages.filter({
      has: page.getByTestId("stopped-notice"),
    });
    await expect(stopped).toHaveCount(1);
    await expect(stopped.getByTestId("stopped-notice")).toHaveText(
      "You stopped this response.",
    );
    await openTrace(stopped);
    await expect(
      stopped.getByTestId("trace-group-state").filter({ hasText: "Stopped" }),
    ).not.toHaveCount(0);
    await expect(chatPage.sendButton).toBeVisible();
    await expect
      .poll(async () => fetchStoppedTurnCount(apiClient, stoppedId), {
        timeout: 60_000,
      })
      .toBe(1);

    await chatPage.sendTurn("Continue.", /\[mock\] Continue\./);
    await expect(page.getByTestId("failure-notice")).toHaveCount(0);
  });

  test("F11 - Close the tab during a background task", async ({
    chatPage,
    apiClient,
    page,
    context,
    siteId,
  }) => {
    const id = await buildOn(
      chatPage,
      siteId,
      prompt("single", S1_TEXT(siteOrganism(siteId))),
    );
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    const [controls] = siteControlSets(siteId);
    if (controls === undefined)
      throw new Error(`the ${siteId} seeds carry no controls`);
    await chatPage.send(
      prompt(
        "controls-test",
        [
          "Test this strategy against my controls.",
          `Positive controls: ${controls.positive_ids.join(" ")}`,
          `Negative controls: ${controls.negative_ids.join(" ")}`,
        ].join("\n"),
      ),
    );
    const running = page.getByTestId("task-row").filter({ hasText: CONTROL_TESTS });
    await expect(running).toHaveCount(1, { timeout: 240_000 });
    await expect(running.getByTestId("task-row-status")).toHaveText(/^(\d+%|Queued)$/);
    await page.close();

    await expect
      .poll(() => controlTaskStatuses(apiClient, id), { timeout: 300_000 })
      .toEqual(["complete"]);
    const reopened = await context.newPage();
    const chat = new ChatPage(reopened);
    await reopened.goto(`/${siteId}/conversation/${id}`);
    await expect(chat.composer).toBeVisible({ timeout: 60_000 });
    const done = reopened.getByTestId("task-row").filter({ hasText: CONTROL_TESTS });
    await expect(done).toHaveCount(1, { timeout: 60_000 });
    await expect(done.getByTestId("task-row-status")).not.toHaveText(
      /^(\d+%|Queued|Failed|)$/,
      { timeout: 240_000 },
    );
    await expect(chat.assistantMessages.filter({ has: done })).toHaveCount(1);
    await expect
      .poll(() => chat.assistantMessages.count(), { timeout: 240_000 })
      .toBeGreaterThan(1);

    const tasksToggle = reopened.getByRole("button", { name: "Open Tasks" });
    if ((await tasksToggle.count()) > 0) await tasksToggle.click();
    const panel = reopened.getByRole("region", { name: "Tasks detail" });
    await expect(
      panel.getByRole("listitem").filter({ hasText: CONTROL_TESTS }),
    ).toContainText("Complete");
  });

  test("F12 - Two accounts stay apart", async ({
    browser,
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    const buildText = prompt("intersect", S2_TEXT(siteOrganism(siteId)));
    const aId = await buildOn(chatPage, siteId, buildText);
    await expectBuild(page, apiClient, aId, siteId, LAYOUTS.intersect);
    const [controls] = siteControlSets(siteId);
    if (controls === undefined)
      throw new Error(`the ${siteId} seeds carry no controls`);
    const imported = await apiClient.post("/api/v1/gene-sets/import", {
      data: {
        name: "UAT F12 gene set",
        siteId,
        rawText: controls.positive_ids.join("\n"),
      },
    });
    expect(imported.ok(), `import ${await imported.text()}`).toBe(true);
    const geneSet = (await imported.json()) as GeneSet;
    await chatPage.sendAndSettle(
      prompt(
        "remember",
        "Please remember that I prefer genes with a predicted signal peptide.",
      ),
    );
    await expect
      .poll(async () => (await memoryItems(apiClient)).length, { timeout: 60_000 })
      .toBeGreaterThan(0);
    const aMemories = await memoryItems(apiClient);

    const other = await signedInUser(browser, `uat-f12-${Date.now()}`, true);
    const bPage = await other.newPage();
    const bChat = new ChatPage(bPage);
    const bSidebar = new SidebarPage(bPage);
    await bPage.goto(`${BASE_URL}/${siteId}/conversation`);
    await expect(bChat.composer).toBeVisible({ timeout: 60_000 });
    await expect(bPage.getByText("No conversations yet.")).toBeVisible({
      timeout: 30_000,
    });
    await expect(bSidebar.item(aId)).toHaveCount(0);
    const bRows = await listConversations(other.request, siteId);
    expect(bRows.map((row) => row.id)).not.toContain(aId);

    await bPage.goto(`${BASE_URL}/${siteId}/conversation/${aId}`);
    await expect(bPage).toHaveURL(`${BASE_URL}/${siteId}/conversation`, {
      timeout: 60_000,
    });
    await expect(bChat.composer).toBeVisible({ timeout: 60_000 });
    await expect(bChat.userMessage(buildText)).toHaveCount(0);

    const bMemories = await memoryItems(other.request);
    expect(bMemories.map((item) => item.key)).toEqual([]);
    await bPage.getByTestId("nav-rail-settings-button").click();
    const settings = bPage.getByRole("dialog", { name: "Settings", exact: true });
    await settings.getByRole("tab", { name: "Memory", exact: true }).click();
    await settings.getByRole("button", { name: /^Preferences/ }).click();
    await expect(settings.getByText("No items stored yet.")).toBeVisible();
    for (const item of aMemories) {
      await expect(settings).not.toContainText(item.value.name);
    }
    await bPage.keyboard.press("Escape");
    await expect(settings).toHaveCount(0);

    await openSlash(bPage, bChat, "/export");
    await bPage.getByTestId("slash-param-option-gene-set-csv").click();
    await expect(bPage.getByText("No gene sets to export.")).toBeVisible();
    const url = `/api/v1/gene-sets?siteId=${siteId}`;
    const bSets = await listBody<GeneSet>(await other.request.get(url), url);
    expect(bSets.map((set) => set.id)).not.toContain(geneSet.id);

    await other.close();
  });

  test("R2 - A VEuPathDB refusal shown where it happened", async ({
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
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    const tm = nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE);
    const valid = paramText(tm, "min_tm");

    await openCanvas(graphPage, siteId, id);
    await graphPage.clickNode(tm.id ?? "");
    await graphPage.expectEditorSheetOpen();
    const minimum = graphPage.editorSheet.locator('input[name="min_tm"]');
    await minimum.clear();
    await minimum.pressSequentially("abc");
    // The number field takes no letters, so nothing reaches the site.
    await expect(minimum).toHaveValue("");
    await expect(graphPage.editorSyncState).not.toHaveAttribute(
      "data-sync-state",
      "error",
    );
    expect(
      paramText(nodeBySearch(await readNodes(apiClient, id), TRANSMEMBRANE), "min_tm"),
    ).toBe(valid);

    await minimum.fill(valid);
    await expect(graphPage.editorSyncState).toHaveText("All changes saved");
    await expect(graphPage.editorFooter).toContainText(
      printed(counts.byStep[tm.id ?? ""] ?? -1),
    );
    await expect(graphPage.strategyPageSyncState).toHaveText("Saved");
    expect((await siteCounts(apiClient, id, siteId)).root).toBe(counts.root);
  });

  test("R6 - A network drop and a reload in the middle of a turn", async ({
    chatPage,
    apiClient,
    page,
    context,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    const id = chatPage.lastStrategyId ?? "";
    await chatPage.send(prompt("intersect", S2_TEXT(siteOrganism(siteId))));
    await expect(page.getByTestId("assistant-status")).toHaveText(/Planning/, {
      timeout: 60_000,
    });
    await context.setOffline(true);
    // The api client is its own request context, so it reads the server offline.
    await expect
      .poll(async () => layoutOf(await storedNodes(apiClient, id)), {
        timeout: 240_000,
      })
      .toEqual(LAYOUTS.intersect);
    await context.setOffline(false);

    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);
    await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(
      0,
      {
        timeout: 240_000,
      },
    );
    await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });

    const reply = chatPage.assistantMessages.filter({
      has: page.getByTestId("data-graph-snapshot"),
    });
    await expect(reply).toHaveCount(1);
    await reply.hover();
    await context.setOffline(true);
    await reply.getByRole("button", { name: "Good response" }).click();
    await expect(page.getByText("The rating was not saved.")).toBeVisible();
    await context.setOffline(false);
  });
});
