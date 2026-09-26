/**
 * UAT flows C1 to C16: every slash command, and the attachments the composer
 * takes and refuses. Counts, step names and gene ids are read from the site
 * and the api; only the model is mocked.
 */

import * as zlib from "node:zlib";

import { siteShortName } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import { type ArcName, arc, prompt } from "../fixtures/arcs";
import { type ApiClient, listConversations } from "../fixtures/api-client";
import { LAYOUTS, TRANSMEMBRANE, layoutOf } from "../fixtures/arc-layouts";
import { expectBuild, openTrace, traceRows } from "../fixtures/build-checks";
import {
  IMAGE_READER,
  MIB,
  type UploadFile,
  attach,
  buildIntersect,
  downloadedText,
  exportFile,
  geneSetsOf,
  importGeneIds,
  loggedUserParts,
  pickExport,
  postAttachment,
  readerIs,
  runSlash,
  seedGeneIds,
  toast,
} from "../fixtures/composer";
import {
  countPattern,
  readAst,
  readConversation,
  readNodes,
  siteControlSets,
  siteOrganism,
} from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";
import { waitForDraftChatRoute } from "../pages/navigation";

const PLACEHOLDER = "Ask about strategies, genes, or data... (try /help)";
const MENU_ORDER = [
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
const NO_STRATEGY = "This conversation has no strategy yet.";
const CLEAR_PROMPT =
  "Clear the current strategy by calling clear_strategy with confirm=true.";
const CLEAR_CARD =
  "Clear the strategy? This removes every step from this conversation and from VEuPathDB.";
const ANALYZE_PROMPT =
  "Analyze my current strategy. Summarize topology and step flow, any weak spots or redundant steps, concrete improvement suggestions, and what I should try next.";
const SUMMARIZE_PROMPT =
  "Summarize this conversation so far: the research question, the strategy I've built, key decisions made, and anything still open.";
const DIAGNOSE_PROMPT =
  "Diagnose my current strategy. Call get_live_strategy_state, walk through each step's count, and identify where results collapse. Suggest the likely cause and concrete fixes.";
const EXPORT_OPTIONS = [
  "Current strategy (JSON)",
  "This conversation (Markdown)",
  "This conversation (JSON)",
  "Latest gene set on this site (CSV)",
  "Latest gene set on this site (TXT)",
];

/** The chooser's accept list for a reader of images and PDFs: no archive. */
const ACCEPT_ALL =
  ".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain,image/png,image/jpeg,image/webp,image/gif,application/pdf";
const NOT_ACCEPTED =
  "PathFinder reads gene-ID lists (.csv, .tsv, .txt), images (PNG, JPEG, WebP, GIF) and PDFs.";
const IMAGE_QUESTION = "Which genes are in this image?";
const PDF_QUESTION = "Which genes are in this document?";

/** The cards a reply can carry; its prose must come before each of them. */
const CARD_SELECTOR = [
  "approval-card",
  "proposal-card",
  "consult-carousel",
  "separation-card",
]
  .map((id) => `[data-testid="${id}"]`)
  .join(",");

const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

type Rgba = [number, number, number, number];

function pngChunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(zlib.crc32(body));
  return Buffer.concat([length, body, crc]);
}

/** An 8-bit RGBA PNG of `rows`, one filter-free scanline per row. */
function encodePng(rows: Rgba[][]): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(rows[0]?.length ?? 0, 0);
  header.writeUInt32BE(rows.length, 4);
  header.writeUInt8(8, 8);
  header.writeUInt8(6, 9);
  const raw = Buffer.from(rows.flatMap((row) => [0, ...row.flat()]));
  return Buffer.concat([
    PNG_SIGNATURE,
    pngChunk("IHDR", header),
    pngChunk("IDAT", zlib.deflateSync(raw)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function paeth(left: number, up: number, upLeft: number): number {
  const estimate = left + up - upLeft;
  const toLeft = Math.abs(estimate - left);
  const toUp = Math.abs(estimate - up);
  const toUpLeft = Math.abs(estimate - upLeft);
  if (toLeft <= toUp && toLeft <= toUpLeft) return left;
  return toUp <= toUpLeft ? up : upLeft;
}

/** The pixels of an 8-bit, non-interlaced RGB or RGBA PNG, row by row. */
function decodePng(png: Buffer): Rgba[] {
  expect(png.subarray(0, 8).equals(PNG_SIGNATURE), "a PNG signature").toBe(true);
  let width = 0;
  let height = 0;
  let colorType = 0;
  const data: Buffer[] = [];
  for (let at = 8; at < png.length;) {
    const length = png.readUInt32BE(at);
    const type = png.toString("ascii", at + 4, at + 8);
    const body = png.subarray(at + 8, at + 8 + length);
    if (type === "IHDR") {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      expect([body.readUInt8(8), body.readUInt8(12)], "bit depth, interlace").toEqual([
        8, 0,
      ]);
      colorType = body.readUInt8(9);
    } else if (type === "IDAT") {
      data.push(body);
    }
    at += 12 + length;
  }
  expect([2, 6], "an RGB or RGBA color type").toContain(colorType);
  const channels = colorType === 6 ? 4 : 3;
  const stride = width * channels;
  const raw = zlib.inflateSync(Buffer.concat(data));
  const out = Buffer.alloc(height * stride);
  for (let y = 0; y < height; y++) {
    const filter = raw.readUInt8(y * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const left = x >= channels ? out.readUInt8(y * stride + x - channels) : 0;
      const up = y > 0 ? out.readUInt8((y - 1) * stride + x) : 0;
      const upLeft =
        x >= channels && y > 0 ? out.readUInt8((y - 1) * stride + x - channels) : 0;
      const predicted = [
        0,
        left,
        up,
        Math.floor((left + up) / 2),
        paeth(left, up, upLeft),
      ][filter];
      if (predicted === undefined) throw new Error(`unknown PNG filter ${filter}`);
      out.writeUInt8(
        (raw.readUInt8(y * (stride + 1) + 1 + x) + predicted) & 0xff,
        y * stride + x,
      );
    }
  }
  const pixels: Rgba[] = [];
  for (let at = 0; at < out.length; at += channels) {
    const alpha = channels === 4 ? out.readUInt8(at + 3) : 255;
    pixels.push([
      out.readUInt8(at),
      out.readUInt8(at + 1),
      out.readUInt8(at + 2),
      alpha,
    ]);
  }
  return pixels;
}

const OPAQUE_PNG = encodePng([
  [
    [255, 255, 255, 255],
    [20, 40, 60, 255],
  ],
  [
    [0, 0, 0, 255],
    [200, 100, 50, 255],
  ],
]);
/** Its first pixel is fully transparent red, which a model reads as black. */
const TRANSPARENT_PNG = encodePng([
  [
    [255, 0, 0, 0],
    [0, 0, 255, 128],
  ],
  [
    [0, 0, 0, 0],
    [20, 40, 60, 255],
  ],
]);
const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const ZIP = Buffer.concat([Buffer.from("PK\u0005\u0006", "latin1"), Buffer.alloc(18)]);

function png(name: string, buffer: Buffer): UploadFile {
  return { name, mimeType: "image/png", buffer };
}

/** The bytes a `data:` URL carries. */
function dataUrlBytes(url: string | undefined): Buffer {
  const [head, body] = (url ?? "").split(",");
  expect(head).toBe("data:image/png;base64");
  return Buffer.from(body ?? "", "base64");
}

/** The echo arc's reply to `text`. */
function echoOf(text: string): RegExp {
  return new RegExp(`\\[mock\\] ${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
}

function conversationId(chatPage: ChatPage): string {
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  return id;
}

async function conversationIds(api: ApiClient, siteId: string): Promise<string[]> {
  return (await listConversations(api, siteId)).map((row) => row.id);
}

async function wdkStepIds(api: ApiClient, id: string) {
  return ((await readConversation(api, id)).steps ?? []).map((step) => step.wdkStepId);
}

/** Send the prefill the command left in the input, with `name`'s token typed after it. */
async function sendPrefill(chatPage: ChatPage, prefill: string, name: ArcName) {
  await expect(chatPage.messageInput).toHaveValue(prefill);
  await chatPage.messageInput.press("End");
  await chatPage.messageInput.pressSequentially(` ${arc(name)}`);
  const message = `${prefill} ${arc(name)}`;
  await expect(chatPage.messageInput).toHaveValue(message);
  await chatPage.sendAndSettle(message);
}

interface ReplyShape {
  prose: string;
  cardBeforeProse: boolean;
}

/** The prose of each reply after the first `from`, and whether a card precedes it. */
async function repliesAfter(chatPage: ChatPage, from: number): Promise<ReplyShape[]> {
  return chatPage.assistantMessages.evaluateAll(
    (replies, { skip, cards }) =>
      replies.slice(skip).map((reply) => {
        const prose = Array.from(reply.querySelectorAll(".prose")).filter(
          (el) => el.closest(cards) === null && el.textContent.trim() !== "",
        );
        const [opening] = prose;
        const cardBeforeProse = Array.from(reply.querySelectorAll(cards)).some(
          (card) =>
            opening === undefined ||
            (card.compareDocumentPosition(opening) &
              Node.DOCUMENT_POSITION_FOLLOWING) !==
              0,
        );
        return {
          prose: prose.map((el) => el.textContent).join("\n"),
          cardBeforeProse,
        };
      }),
    { skip: from, cards: CARD_SELECTOR },
  );
}

test.describe("Slash commands", () => {
  test("C1 - /help and the menu", async ({ page, chatPage, siteId }) => {
    await chatPage.startOn(siteId);
    await expect(chatPage.messageInput).toHaveAttribute("placeholder", PLACEHOLDER);

    await chatPage.messageInput.fill("/");
    const menu = page.getByRole("listbox", { name: "Slash commands" });
    await expect(menu.getByRole("option")).toHaveText(
      MENU_ORDER.map((name) => new RegExp(`^/${name}`)),
    );
    await expect(page.getByTestId("slash-item-export")).toContainText(
      "/save /download",
    );
    await expect(page.getByTestId("slash-item-help")).toContainText("/?");
    await expect(page.getByTestId("slash-item-new")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await chatPage.messageInput.press("ArrowDown");
    await expect(page.getByTestId("slash-item-rename")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await chatPage.messageInput.press("Escape");
    await expect(chatPage.messageInput).toHaveValue("");

    await chatPage.messageInput.fill("/");
    for (const name of ["clear", "analyze", "diagnose", "explain"]) {
      await expect(page.getByTestId(`slash-item-${name}`)).toBeDisabled();
      await expect(page.getByTestId(`slash-item-${name}`)).toHaveAttribute(
        "data-disabled",
        "true",
      );
    }
    await expect(page.getByTestId("slash-item-summarize")).toBeEnabled();
    await page.getByTestId("slash-item-clear").hover();
    await expect(page.getByRole("tooltip")).toHaveText(NO_STRATEGY);

    await runSlash(page, chatPage, "/hel");
    await expect(chatPage.messageInput).toHaveValue("/");
    await expect(menu.getByRole("option")).toHaveCount(MENU_ORDER.length);

    await chatPage.messageInput.fill("/xyz");
    await chatPage.messageInput.press("Enter");
    await expect(chatPage.composer.getByRole("alert")).toHaveText(
      "No command /xyz. Type / to see the list.",
    );
    await expect(chatPage.messageInput).toHaveValue("/xyz");
    await expect(chatPage.userMessages).toHaveCount(0);
  });

  test("C2 - /new", async ({ page, chatPage, apiClient, siteId }) => {
    await chatPage.startOn(siteId);
    await runSlash(page, chatPage, "/new");
    await waitForDraftChatRoute(page);
    expect(new URL(page.url()).searchParams.get("assistant")).toBe(null);
    await expect(chatPage.messageInput).toHaveValue("");
    await expect(page.getByTestId("chat-empty-blurb")).toHaveText(
      `Build and refine multi-step ${siteShortName(siteId)} search strategies with guided parameter selection and validation.`,
    );
    await expect(page.getByTestId("chat-assistant-label")).toHaveCount(0);

    const before = await conversationIds(apiClient, siteId);
    await runSlash(page, chatPage, "/help");
    await expect(chatPage.messageInput).toHaveValue("/");
    await chatPage.messageInput.fill("/new");
    await chatPage.messageInput.press("Enter");
    await waitForDraftChatRoute(page);
    expect(await conversationIds(apiClient, siteId)).toEqual(before);
  });

  test("C3 - /rename", async ({ page, chatPage, apiClient, siteId }) => {
    const name = "UAT rename C3";
    await chatPage.startOn(siteId);
    const id = conversationId(chatPage);
    const stepper = page.getByTestId("slash-param-stepper");

    await runSlash(page, chatPage, "/rename");
    await page.getByTestId("slash-param-text-name").fill(name);
    await stepper.getByRole("button", { name: "Next" }).click();
    await expect(toast(page, `Renamed to "${name}".`)).toBeVisible();
    expect((await readConversation(apiClient, id)).name).toBe(name);
    await expect(
      page.locator(`[data-testid="conversation-item"][data-conversation-id="${id}"]`),
    ).toContainText(name);

    await runSlash(page, chatPage, "/rename");
    await stepper.getByRole("button", { name: "Next" }).click();
    await expect(toast(page, "Name cannot be empty.")).toBeVisible();
    expect((await readConversation(apiClient, id)).name).toBe(name);
  });

  test("C4 - /export with no strategy", async ({ page, chatPage, siteId }) => {
    await chatPage.startOn(siteId);
    const downloads: string[] = [];
    page.on("download", (file) => downloads.push(file.suggestedFilename()));

    await runSlash(page, chatPage, "/export");
    await expect(
      page.getByRole("group", { name: "What to export" }).getByRole("button"),
    ).toHaveText(EXPORT_OPTIONS);
    await page.getByTestId("slash-param-option-strategy-json").click();
    await expect(toast(page, NO_STRATEGY)).toBeVisible();
    expect(downloads).toEqual([]);
  });

  test("C6 - /export of the latest gene set", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    await pickExport(page, chatPage, "gene-set-csv");
    await expect(toast(page, "No gene sets to export.")).toBeVisible();

    await importGeneIds(
      page,
      chatPage,
      "UAT export C6",
      seedGeneIds(siteId, 3).join("\n"),
    );
    await expect
      .poll(async () => (await geneSetsOf(apiClient, siteId)).map((set) => set.name))
      .toEqual(["UAT export C6"]);
    for (const format of ["csv", "txt"]) {
      const file = await exportFile(page, chatPage, `gene-set-${format}`);
      expect(file.suggestedFilename()).toMatch(new RegExp(`\\.${format}$`));
      await expect(
        toast(page, new RegExp(`^Downloading \\S+\\.${format}$`)),
      ).toBeVisible();
    }
  });

  test("C7 - /import", async ({ page, chatPage, apiClient, siteId }) => {
    const name = "UAT import C7";
    const ids = seedGeneIds(siteId, 3);
    const [first = "", ...rest] = ids;
    await chatPage.startOn(siteId);

    await importGeneIds(page, chatPage, "", ids.join("\n"));
    await expect(toast(page, "Name required.")).toBeVisible();
    await importGeneIds(page, chatPage, name, "");
    await expect(toast(page, "Paste at least one gene ID.")).toBeVisible();
    expect(await geneSetsOf(apiClient, siteId)).toEqual([]);

    await importGeneIds(page, chatPage, name, `${first}\n${rest.join(", ")}`);
    await expect(toast(page, `Imported "${name}" with 3 gene IDs.`)).toBeVisible();
    expect(
      (await geneSetsOf(apiClient, siteId)).map((set) => [set.name, set.geneIds]),
    ).toEqual([[name, ids]]);
  });
});

test.describe("Slash commands on a built strategy", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("C5 - /export of the conversation and the strategy", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    const { id } = await buildIntersect(page, chatPage, apiClient, siteId);

    const markdown = await exportFile(page, chatPage, "chat-md");
    expect(markdown.suggestedFilename()).toBe(`chat-${id}.md`);
    await expect(toast(page, "Conversation exported.")).toBeVisible();
    const lines = (await downloadedText(markdown)).split("\n");

    const json = await exportFile(page, chatPage, "chat-json");
    expect(json.suggestedFilename()).toBe(`chat-${id}.json`);
    const roles = (JSON.parse(await downloadedText(json)) as { role: string }[]).map(
      (message) => message.role,
    );
    expect(roles.filter((role) => role === "user")).toHaveLength(1);
    expect(lines[0]).toBe("# PathFinder conversation export");
    expect(
      lines.filter((line) => line === "## user" || line === "## assistant"),
    ).toEqual(roles.map((role) => `## ${role}`));

    const strategy = await exportFile(page, chatPage, "strategy-json");
    expect(strategy.suggestedFilename()).toBe(`strategy-${id}.json`);
    await expect(toast(page, "Strategy downloaded.")).toBeVisible();
    expect(JSON.parse(await downloadedText(strategy))).toEqual(
      await readAst(apiClient, id),
    );
  });

  test("C8 - /clear", async ({ page, chatPage, apiClient, siteId }) => {
    const { id } = await buildIntersect(page, chatPage, apiClient, siteId);

    await runSlash(page, chatPage, "/clear");
    await expect(chatPage.userMessage(CLEAR_PROMPT)).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(
      page.getByTestId("approval-card").getByTestId("approval-card-title"),
    ).toHaveText(CLEAR_CARD, { timeout: 120_000 });
    expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.intersect);
  });

  test("C9 - /analyze", async ({ page, chatPage, apiClient, siteId }) => {
    const { id } = await buildIntersect(page, chatPage, apiClient, siteId);
    const stepsBefore = await wdkStepIds(apiClient, id);
    const repliesBefore = await chatPage.assistantMessages.count();

    await runSlash(page, chatPage, "/analyze");
    await expect(chatPage.userMessages).toHaveCount(1);
    await sendPrefill(chatPage, ANALYZE_PROMPT, "impact");

    const replies = await repliesAfter(chatPage, repliesBefore);
    expect(replies.length).toBeGreaterThan(0);
    expect(replies.map((reply) => reply.cardBeforeProse)).not.toContain(true);
    expect(
      replies
        .map((reply) => reply.prose)
        .join("")
        .trim(),
    ).not.toBe("");
    expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.intersect);
    expect(await wdkStepIds(apiClient, id)).toEqual(stepsBefore);
  });

  test("C10 - /summarize", async ({ page, chatPage, apiClient, siteId }) => {
    const { id, counts } = await buildIntersect(page, chatPage, apiClient, siteId);
    const stepsBefore = await wdkStepIds(apiClient, id);
    const figures = await page.getByTestId("data-graph-snapshot").count();
    const repliesBefore = await chatPage.assistantMessages.count();

    await runSlash(page, chatPage, "/summarize");
    await expect(chatPage.userMessages).toHaveCount(1);
    await sendPrefill(chatPage, SUMMARIZE_PROMPT, "recap");

    // The reply paints in pieces, so the read retries until the count is in.
    await expect
      .poll(async () =>
        (await repliesAfter(chatPage, repliesBefore))
          .map((reply) => reply.prose)
          .join("\n"),
      )
      .toMatch(countPattern(counts.root));
    await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(figures);
    expect(await wdkStepIds(apiClient, id)).toEqual(stepsBefore);
  });

  test("C11 - /diagnose and /explain", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    await chatPage.sendAndSettle(
      prompt(
        "zero-then-relax",
        `Find ${siteOrganism(siteId)} genes with 99 to 99 transmembrane domains.`,
      ),
    );
    const id = conversationId(chatPage);
    const counts = await expectBuild(
      page,
      apiClient,
      id,
      siteId,
      LAYOUTS["zero-then-relax"],
    );
    expect(counts.root).toBe(0);
    const empty = (await readNodes(apiClient, id)).filter(
      (node) => node.searchName === TRANSMEMBRANE && counts.byStep[node.id ?? ""] === 0,
    );
    expect(empty).toHaveLength(1);
    const stepName = empty.map((node) => node.displayName ?? "").join("");
    expect(stepName).not.toBe("");
    const repliesBefore = await chatPage.assistantMessages.count();

    await runSlash(page, chatPage, "/diagnose");
    await sendPrefill(chatPage, DIAGNOSE_PROMPT, "recap");
    await expect
      .poll(async () =>
        (await repliesAfter(chatPage, repliesBefore))
          .map((reply) => reply.prose)
          .join("\n"),
      )
      .toContain(stepName);

    await runSlash(page, chatPage, "/explain");
    const hint = page.getByTestId("slash-param-text-stepHint");
    await hint.fill("the transmembrane step");
    await hint.press("Enter");
    await expect(chatPage.messageInput).toHaveValue(
      "Explain what the transmembrane step does and why it matters biologically.",
    );
    await expect(chatPage.userMessages).toHaveCount(2);
  });

  test("C12 - A gene-id list", async ({ page, chatPage, siteId }) => {
    const controls = siteControlSets(siteId).find(
      (set) => set.positive_ids.length >= 2,
    );
    const ids = controls?.positive_ids.slice(0, 2) ?? [];
    expect(ids).toHaveLength(2);
    const request = "Use these genes as my positive controls.";
    await chatPage.startOn(siteId);

    await chatPage.attachGeneIdFile(
      "controls.csv",
      ["geneId,product", ...ids.map((id) => `${id},control`)].join("\n"),
    );
    await expect(page.getByTestId("composer-attachment")).toHaveText(["controls.csv"]);
    await chatPage.sendAndSettle(request);

    const sent = chatPage.userMessage(request);
    await expect(sent).toContainText(
      `Attached gene-ID list from controls.csv: ${ids.join(", ")}`,
    );
    const reply = chatPage.assistantMessages;
    await expect(reply).toHaveCount(1);
    await openTrace(reply);
    await expect(traceRows(reply, "Build control set")).toHaveCount(1);
  });
});

test.describe("Attachments", () => {
  test.beforeEach(async ({ page, chatPage, settingsPage, siteId }) => {
    await chatPage.startOn(siteId);
    await readerIs(page, settingsPage, IMAGE_READER.name);
  });

  test("C13 - An image", async ({ page, chatPage, apiClient, siteId }) => {
    await expect(page.getByTestId("add-attachment")).toHaveAccessibleName(
      "Attach a gene-ID list, an image or a PDF",
    );
    await attach(page, [png("table.png", OPAQUE_PNG)]);
    await expect(page.getByTestId("composer-attachment")).toHaveText(["table.png"]);
    await chatPage.sendTurn(IMAGE_QUESTION, echoOf(IMAGE_QUESTION));

    const thumbnail = chatPage
      .userMessage(IMAGE_QUESTION)
      .getByTestId("user-attachment-image");
    await expect(thumbnail).toHaveAttribute("alt", "table.png");
    const parts = await loggedUserParts(apiClient, conversationId(chatPage));
    expect(parts).toMatchObject([
      { type: "text", text: IMAGE_QUESTION },
      { type: "file", filename: "table.png", mediaType: "image/png" },
    ]);
    const [, opaque] = parts;
    expect(dataUrlBytes(opaque?.url).toString("base64")).toBe(
      OPAQUE_PNG.toString("base64"),
    );
    await page.reload();
    await expect(thumbnail).toHaveAttribute("alt", "table.png", { timeout: 60_000 });

    await chatPage.newChat(siteId);
    await attach(page, [png("table-transparent.png", TRANSPARENT_PNG)]);
    await chatPage.sendTurn(IMAGE_QUESTION, echoOf(IMAGE_QUESTION));
    const [, flattened] = await loggedUserParts(apiClient, conversationId(chatPage));
    expect(flattened).toMatchObject({
      type: "file",
      filename: "table-transparent.png",
      mediaType: "image/png",
    });
    const pixels = decodePng(dataUrlBytes(flattened?.url));
    expect(pixels).toHaveLength(4);
    expect(pixels.map((pixel) => pixel[3])).toEqual([255, 255, 255, 255]);
    expect(pixels[0]).toEqual([255, 255, 255, 255]);
  });

  test("C14 - A PDF", async ({ page, chatPage, apiClient }) => {
    await attach(page, [
      { name: "table.pdf", mimeType: "application/pdf", buffer: PDF },
    ]);
    await expect(page.getByTestId("composer-attachment")).toHaveText(["table.pdf"]);
    await chatPage.sendTurn(PDF_QUESTION, echoOf(PDF_QUESTION));

    const chip = chatPage.userMessage(PDF_QUESTION).getByTestId("user-attachment-file");
    await expect(chip).toHaveText("table.pdf");
    expect(await loggedUserParts(apiClient, conversationId(chatPage))).toMatchObject([
      { type: "text", text: PDF_QUESTION },
      { type: "file", filename: "table.pdf", mediaType: "application/pdf" },
    ]);
    await page.reload();
    await expect(chip).toHaveText("table.pdf", { timeout: 60_000 });
  });

  test("C15 - A kind PathFinder refuses", async ({ page, apiClient, siteId }) => {
    const zip = { name: "table.zip", mimeType: "application/zip", buffer: ZIP };
    await expect(page.getByTestId("add-attachment")).toHaveAccessibleName(
      "Attach a gene-ID list, an image or a PDF",
    );
    expect(await attach(page, [zip])).toBe(ACCEPT_ALL);
    await expect(toast(page, NOT_ACCEPTED)).toBeVisible();
    await expect(page.getByTestId("composer-attachment")).toHaveCount(0);

    const refused = await postAttachment(apiClient, siteId, IMAGE_READER.id, zip);
    expect(refused.status()).toBe(422);
    expect(await refused.json()).toMatchObject({
      code: "ATTACHMENT_NOT_READABLE",
      detail:
        "table.zip is application/zip; PathFinder reads PNG, JPEG, WebP and GIF images and PDF documents.",
    });
  });

  test("C16 - The size and count caps", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    const tooBig = "big.png is 11.0 MB; one attachment can be at most 10 MB.";
    const big = png("big.png", Buffer.alloc(11 * MIB));
    await attach(page, [big]);
    await expect(toast(page, tooBig)).toBeVisible();
    await expect(page.getByTestId("composer-attachment")).toHaveCount(0);
    const large = await postAttachment(apiClient, siteId, IMAGE_READER.id, big);
    expect(large.status()).toBe(413);
    expect(await large.json()).toMatchObject({
      code: "ATTACHMENT_TOO_LARGE",
      detail: tooBig,
    });

    const seven = Array.from({ length: 7 }, (_, n) => `small-${n}.png`);
    await attach(
      page,
      seven.map((name) => png(name, OPAQUE_PNG)),
    );
    await expect(chatPage.composer.getByRole("alert")).toHaveText(
      "One message can carry at most 6 attachments; this one has 7.",
    );
    await chatPage.messageInput.fill(IMAGE_QUESTION);
    await expect(chatPage.sendButton).toBeDisabled();
    await chatPage.messageInput.press("Enter");
    await expect(chatPage.userMessages).toHaveCount(0);

    for (const name of seven) {
      await page
        .getByTestId("composer-attachment")
        .filter({ hasText: name })
        .getByRole("button", { name: "Remove attachment" })
        .click();
    }
    await expect(page.getByTestId("composer-attachment")).toHaveCount(0);
    await attach(
      page,
      ["heavy-1.png", "heavy-2.png", "heavy-3.png"].map((name) =>
        png(name, Buffer.alloc(7 * MIB)),
      ),
    );
    await expect(chatPage.composer.getByRole("alert")).toHaveText(
      "These attachments come to 21.0 MB; one message can carry at most 20 MB.",
    );
    await expect(chatPage.sendButton).toBeDisabled();
    await expect(chatPage.userMessages).toHaveCount(0);
  });
});
