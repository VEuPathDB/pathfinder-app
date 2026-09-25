import * as fs from "node:fs";

import type { Download, Page } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import { type ApiClient, listConversations } from "../fixtures/api-client";
import { MOCK_PLAN_PROMPT, MOCK_PLAN_REPLY } from "../fixtures/mock-prompts";
import type { ChatPage } from "../pages/chat.page";
import { currentSiteId, waitForDraftChatRoute } from "../pages/navigation";

/** Every slash command, driven from the composer with the mock model. Each test
 * asserts what the command changed: the thread, the route, a row, or a file. */

/** The registry, in the order the menu lists it. */
const ALL_COMMANDS = [
  "new",
  "rename",
  "export",
  "import",
  "help",
  "clear",
  "analyze",
  "summarize",
  "diagnose",
  "explain",
];

const CLEAR_PROMPT =
  "Clear the current strategy by calling clear_strategy with confirm=true.";

async function typeCommand(chatPage: ChatPage, text: string) {
  await chatPage.messageInput.fill(text);
}

async function runSlash(page: Page, chatPage: ChatPage, text: string) {
  await typeCommand(chatPage, text);
  await expect(page.getByTestId("slash-popover")).toBeVisible();
  await chatPage.messageInput.press("Enter");
}

async function exportChoice(page: Page, chatPage: ChatPage, value: string) {
  await runSlash(page, chatPage, "/export");
  await page.getByTestId(`slash-param-option-${value}`).click();
}

function downloadedText(file: Download): Promise<string> {
  return file.path().then((p) => fs.readFileSync(p, "utf8"));
}

async function conversationIds(
  apiClient: ApiClient,
  siteId: string,
): Promise<string[]> {
  return (await listConversations(apiClient, siteId)).map((c) => c.id);
}

test.describe("Slash commands on a chat without a strategy", () => {
  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("/help lists every command and sends nothing", async ({ page, chatPage }) => {
    await runSlash(page, chatPage, "/help");
    await expect(chatPage.messageInput).toHaveValue("/");
    const items = page.getByTestId("slash-popover").getByRole("option");
    await expect(items).toHaveText(ALL_COMMANDS.map((name) => new RegExp(`^/${name}`)));
    await expect(chatPage.userMessages).toHaveCount(0);
  });

  test("Enter on a typed prefix runs the highlighted command", async ({
    page,
    chatPage,
  }) => {
    await runSlash(page, chatPage, "/hel");
    await expect(chatPage.messageInput).toHaveValue("/");
    await expect(page.getByTestId("slash-popover").getByRole("option")).toHaveCount(
      ALL_COMMANDS.length,
    );
    await expect(chatPage.userMessages).toHaveCount(0);
  });

  test("an unknown command is refused in the composer and sends nothing", async ({
    page,
    chatPage,
  }) => {
    await typeCommand(chatPage, "/xyz");
    await chatPage.messageInput.press("Enter");
    await expect(page.getByRole("alert").filter({ hasText: "No command" })).toHaveText(
      "No command /xyz. Type / to see the list.",
    );
    await expect(chatPage.messageInput).toHaveValue("/xyz");
    await expect(chatPage.userMessages).toHaveCount(0);
  });

  test("/new opens a new chat", async ({ page, chatPage }) => {
    await runSlash(page, chatPage, "/new");
    await waitForDraftChatRoute(page);
    await expect(chatPage.messageInput).toHaveValue("");
  });

  test("/rename renames the chat in the list and on the server", async ({
    page,
    chatPage,
    apiClient,
  }) => {
    await runSlash(page, chatPage, "/rename");
    const name = page.getByTestId("slash-param-text-name");
    await name.fill("Kinase follow-up");
    await name.press("Enter");
    await expect(page.getByText('Renamed to "Kinase follow-up".')).toBeVisible();
    const id = chatPage.lastStrategyId ?? "";
    const resp = await apiClient.get(`/api/v1/conversations/${id}`);
    expect(((await resp.json()) as { name: string }).name).toBe("Kinase follow-up");
    await expect(
      page.locator(`[data-testid="conversation-item"][data-conversation-id="${id}"]`),
    ).toContainText("Kinase follow-up");
  });

  test("/export writes the thread as Markdown and as JSON", async ({
    page,
    chatPage,
  }) => {
    await chatPage.sendTurn("hello export", /\[mock\] hello export/);
    const id = chatPage.lastStrategyId ?? "";

    const markdown = page.waitForEvent("download");
    await exportChoice(page, chatPage, "chat-md");
    const md = await markdown;
    expect(md.suggestedFilename()).toBe(`chat-${id}.md`);
    expect(await downloadedText(md)).toContain("[mock] hello export");

    const json = page.waitForEvent("download");
    await exportChoice(page, chatPage, "chat-json");
    const thread = JSON.parse(await downloadedText(await json)) as { role: string }[];
    expect(thread.map((m) => m.role)).toEqual(["user", "assistant"]);
  });

  test("/export refuses the strategy of a chat that has none", async ({
    page,
    chatPage,
  }) => {
    await chatPage.sendTurn("first chat", /\[mock\] first chat/);
    await chatPage.newChat();
    await chatPage.sendTurn("second chat", /\[mock\] second chat/);
    const downloads: string[] = [];
    page.on("download", (d) => downloads.push(d.suggestedFilename()));
    await exportChoice(page, chatPage, "strategy-json");
    await expect(
      page.getByText("This conversation has no strategy yet."),
    ).toBeVisible();
    expect(downloads).toEqual([]);
  });

  test("/import stores the ids and /export writes them back", async ({
    page,
    chatPage,
    apiClient,
  }) => {
    const siteId = currentSiteId(page);
    await runSlash(page, chatPage, "/import");
    const name = page.getByTestId("slash-param-text-name");
    await name.fill("slash import");
    await name.press("Enter");
    await page
      .getByTestId("slash-param-textarea-rawText")
      .fill("PF3D7_0102600\nPF3D7_0709000, PF3D7_1133400");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(
      page.getByText('Imported "slash import" with 3 gene IDs.'),
    ).toBeVisible();
    const sets = (await (
      await apiClient.get(`/api/v1/gene-sets?siteId=${siteId}`)
    ).json()) as { name: string; geneIds: string[] }[];
    expect(sets.map((s) => [s.name, s.geneIds])).toEqual([
      ["slash import", ["PF3D7_0102600", "PF3D7_0709000", "PF3D7_1133400"]],
    ]);

    for (const format of ["csv", "txt"]) {
      const download = page.waitForEvent("download");
      await exportChoice(page, chatPage, `gene-set-${format}`);
      const file = await download;
      expect(file.suggestedFilename()).toMatch(new RegExp(`\\.${format}$`));
      expect(await downloadedText(file)).toContain("PF3D7_1133400");
    }
  });

  test("the strategy commands wait for a strategy", async ({ page, chatPage }) => {
    await typeCommand(chatPage, "/");
    for (const name of ["clear", "analyze", "diagnose", "explain"]) {
      await expect(page.getByTestId(`slash-item-${name}`)).toBeDisabled();
    }
    await expect(page.getByTestId("slash-item-summarize")).toBeEnabled();
    await typeCommand(chatPage, "/clear");
    await chatPage.messageInput.press("Enter");
    await expect(chatPage.messageInput).toHaveValue("/clear");
    await expect(chatPage.userMessages).toHaveCount(0);
  });

  test("/summarize prefills its prompt and sends it on Send", async ({
    page,
    chatPage,
  }) => {
    await runSlash(page, chatPage, "/summarize");
    await expect(chatPage.messageInput).toHaveValue(
      /^Summarize this conversation so far/,
    );
    await expect(chatPage.userMessages).toHaveCount(0);
    await chatPage.sendButton.click();
    await chatPage.awaitTurn(/\[mock\] Summarize this conversation so far/);
    await expect(chatPage.userMessages).toHaveCount(1);
  });
});

test.describe("Slash commands on a chat with a strategy", () => {
  test("every strategy command runs once against the built strategy", async ({
    page,
    chatPage,
  }) => {
    await chatPage.goto();
    await chatPage.newChat();
    await chatPage.sendTurn(MOCK_PLAN_PROMPT, MOCK_PLAN_REPLY);

    const strategy = page.waitForEvent("download");
    await exportChoice(page, chatPage, "strategy-json");
    const file = await strategy;
    expect(file.suggestedFilename()).toBe(`strategy-${chatPage.lastStrategyId}.json`);
    expect(await downloadedText(file)).toContain('"searchName"');

    await runSlash(page, chatPage, "/analyze");
    await expect(chatPage.messageInput).toHaveValue(/^Analyze my current strategy\./);
    await runSlash(page, chatPage, "/diagnose");
    await expect(chatPage.messageInput).toHaveValue(/^Diagnose my current strategy\./);
    await runSlash(page, chatPage, "/explain");
    const hint = page.getByTestId("slash-param-text-stepHint");
    await hint.fill("the organism step");
    await hint.press("Enter");
    await expect(chatPage.messageInput).toHaveValue(
      "Explain what the organism step does and why it matters biologically.",
    );
    await expect(chatPage.userMessages).toHaveCount(1);

    await runSlash(page, chatPage, "/clear");
    await chatPage.awaitTurn(/\[mock\] Clear the current strategy/);
    await expect(chatPage.userMessages.filter({ hasText: CLEAR_PROMPT })).toHaveCount(
      1,
    );
  });
});

test.describe("Slash commands on a draft chat", () => {
  test("/help and /new create no conversation", async ({
    page,
    chatPage,
    apiClient,
  }) => {
    await chatPage.goto();
    await page.goto(`/${currentSiteId(page)}/conversation`);
    await waitForDraftChatRoute(page);
    const before = await conversationIds(apiClient, currentSiteId(page));
    await runSlash(page, chatPage, "/help");
    await expect(chatPage.messageInput).toHaveValue("/");
    await chatPage.messageInput.fill("/new");
    await chatPage.messageInput.press("Enter");
    await waitForDraftChatRoute(page);
    expect(await conversationIds(apiClient, currentSiteId(page))).toEqual(before);
  });
});
