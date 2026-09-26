/**
 * What the composer and gene-set specs share: a slash command run from the
 * composer, the files an export downloads, attachments, a chat body posted
 * straight to the api, and the S2 build both families start from.
 */

import * as fs from "node:fs";

import { type Download, type Locator, type Page, expect } from "@playwright/test";
import type { GeneSet } from "@pathfinder/shared";

import type { ApiClient } from "./api-client";
import { prompt } from "./arcs";
import { LAYOUTS } from "./arc-layouts";
import { expectBuild } from "./build-checks";
import { type SiteCounts, siteControlSets, siteOrganism } from "./site-reads";
import type { ChatPage } from "../pages/chat.page";
import type { SettingsPage } from "../pages/settings.page";

export const MIB = 1024 * 1024;

/** The model every attachment flow reads the message with. */
export const IMAGE_READER = { name: "GPT-5.6 Luna", id: "openai:gpt-5.6-luna" };

/** The toast that reads exactly `text`. */
export function toast(page: Page, text: string | RegExp): Locator {
  return page.getByText(text, { exact: true });
}

/** The researcher's gene sets on one site, newest first, as the api lists them. */
export async function geneSetsOf(api: ApiClient, siteId: string): Promise<GeneSet[]> {
  const resp = await api.get(`/api/v1/gene-sets?siteId=${siteId}`);
  expect(resp.status(), `gene sets of ${siteId}`).toBe(200);
  return (await resp.json()) as GeneSet[];
}

/** Type a slash command, wait for the menu, and pick the highlighted row. */
export async function runSlash(page: Page, chatPage: ChatPage, text: string) {
  await chatPage.messageInput.fill(text);
  await expect(page.getByTestId("slash-popover")).toBeVisible();
  await chatPage.messageInput.press("Enter");
}

/** Pick one `/export` option; `value` is the option's testid suffix. */
export async function pickExport(page: Page, chatPage: ChatPage, value: string) {
  await runSlash(page, chatPage, "/export");
  await page.getByTestId(`slash-param-option-${value}`).click();
}

/** Pick one `/export` option and return the file it downloads. */
export async function exportFile(
  page: Page,
  chatPage: ChatPage,
  value: string,
): Promise<Download> {
  const download = page.waitForEvent("download");
  await pickExport(page, chatPage, value);
  return download;
}

export async function downloadedText(file: Download): Promise<string> {
  return fs.readFileSync(await file.path(), "utf8");
}

/** The gene ids of an exported CSV or TXT gene set, in file order. */
export function exportedIds(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== "" && line !== "gene_id");
}

/** Run `/import` with `name` and the pasted `rawText`, and press Continue. */
export async function importGeneIds(
  page: Page,
  chatPage: ChatPage,
  name: string,
  rawText: string,
) {
  await runSlash(page, chatPage, "/import");
  const nameInput = page.getByTestId("slash-param-text-name");
  await nameInput.fill(name);
  await nameInput.press("Enter");
  await page.getByTestId("slash-param-textarea-rawText").fill(rawText);
  await page
    .getByTestId("slash-param-stepper")
    .getByRole("button", { name: "Continue" })
    .click();
}

/** The first `count` distinct positive control ids of the site's seeds. */
export function seedGeneIds(siteId: string, count: number): string[] {
  const ids = [...new Set(siteControlSets(siteId).flatMap((set) => set.positive_ids))];
  if (ids.length < count) {
    throw new Error(`the ${siteId} seeds carry fewer than ${count} control ids`);
  }
  return ids.slice(0, count);
}

/** Put `modelName` on the role that reads the user's message. */
export async function readerIs(
  page: Page,
  settingsPage: SettingsPage,
  modelName: string,
) {
  await settingsPage.open();
  await settingsPage.openTab("Model");
  const picker = page
    .getByTestId("phase-row-lead")
    .getByRole("button", { name: /^Select model:/ });
  await picker.click();
  await page
    .getByRole("row")
    .filter({ hasText: modelName })
    .getByRole("button", { name: "Select" })
    .click();
  await expect(picker).toHaveAccessibleName(`Select model: ${modelName}`);
  await settingsPage.close();
}

export interface UploadFile {
  name: string;
  mimeType: string;
  buffer: Buffer;
}

/** Attach `files` through the composer's chooser; returns the accept list it offered. */
export async function attach(page: Page, files: UploadFile[]): Promise<string> {
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByTestId("add-attachment").click();
  const chooser = await chooserPromise;
  const accept = (await chooser.element().getAttribute("accept")) ?? "";
  await chooser.setFiles(files);
  return accept;
}

/** Post one user message carrying `file` to the chat api, past the composer. */
export async function postAttachment(
  api: ApiClient,
  siteId: string,
  lead: string,
  file: UploadFile,
) {
  return api.post("/api/v1/chat", {
    data: {
      conversationId: crypto.randomUUID(),
      siteId,
      phaseModels: { lead },
      messages: [
        {
          id: crypto.randomUUID(),
          role: "user",
          parts: [
            { type: "text", text: "which genes are in this file?" },
            {
              type: "file",
              mediaType: file.mimeType,
              filename: file.name,
              url: `data:${file.mimeType};base64,${file.buffer.toString("base64")}`,
            },
          ],
        },
      ],
    },
  });
}

/** One part of a user message as the event log recorded it. */
export interface LoggedPart {
  type: string;
  text?: string;
  filename?: string;
  mediaType?: string;
  url?: string;
}

/** The parts of the conversation's first user message, from its event log. */
export async function loggedUserParts(
  api: ApiClient,
  conversationId: string,
): Promise<LoggedPart[]> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/events/snapshot`);
  expect(resp.status(), `events of ${conversationId}`).toBe(200);
  const { chunks } = (await resp.json()) as {
    chunks: { type: string; message?: { parts?: LoggedPart[] } }[];
  };
  return chunks.find((c) => c.type === "user-message")?.message?.parts ?? [];
}

/** The S2 request: two searches of the site's organism, INTERSECT. */
export function intersectRequest(siteId: string): string {
  return prompt(
    "intersect",
    `Find ${siteOrganism(siteId)} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`,
  );
}

/** Build S2 on a fresh conversation of the site; returns its id and the site's counts. */
export async function buildIntersect(
  page: Page,
  chatPage: ChatPage,
  api: ApiClient,
  siteId: string,
): Promise<{ id: string; counts: SiteCounts }> {
  await chatPage.startOn(siteId);
  await chatPage.sendAndSettle(intersectRequest(siteId));
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  const counts = await expectBuild(page, api, id, siteId, LAYOUTS.intersect);
  return { id, counts };
}
