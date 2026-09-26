/**
 * What a spec reads from the site and from the api to compare a panel with:
 * the counts the site answers for a strategy, the conversation as stored, and
 * the values the site's seed catalog names.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { expect } from "@playwright/test";
import type {
  ConversationResponse,
  SiteResponse,
  StepCountsResponse,
  StrategyAst,
} from "@pathfinder/shared";

import { type ApiClient, CSRF_HEADERS } from "./api-client";
import { type AstNode, astNodes } from "./ast";

/** The stored conversation, with its steps and the counts the build recorded. */
export async function readConversation(
  api: ApiClient,
  conversationId: string,
): Promise<ConversationResponse> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}`);
  expect(resp.status(), `conversation ${conversationId}`).toBe(200);
  return (await resp.json()) as ConversationResponse;
}

/** The stored strategy tree. */
export async function readAst(
  api: ApiClient,
  conversationId: string,
): Promise<StrategyAst> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/ast`);
  expect(resp.status(), `ast of ${conversationId}`).toBe(200);
  return (await resp.json()) as StrategyAst;
}

/** Every node of the stored tree. */
export async function readNodes(
  api: ApiClient,
  conversationId: string,
): Promise<AstNode[]> {
  return astNodes(await api.get(`/api/v1/conversations/${conversationId}/ast`));
}

/**
 * The stored tree's nodes, or none while the conversation holds no strategy.
 * `expect.poll` stops on a throw, so a read polled across a running turn uses this.
 */
export async function storedNodes(
  api: ApiClient,
  conversationId: string,
): Promise<AstNode[]> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/ast`);
  if (resp.status() === 404) return [];
  return astNodes(resp);
}

/** The counts the site answers now for every step of the stored tree, and its root. */
export interface SiteCounts {
  root: number;
  byStep: Record<string, number | null>;
}

/**
 * Run the stored tree on the site and read each step's count. The api runs it
 * in WDK, so the numbers are the site's, not the ones the build recorded. A
 * step the site did not count in one pass is asked again until it answers.
 */
export async function siteCounts(
  api: ApiClient,
  conversationId: string,
  siteId: string,
): Promise<SiteCounts> {
  let rootId = "";
  let counts: StepCountsResponse["counts"] = {};
  await expect
    .poll(
      async () => {
        const ast = await readAst(api, conversationId);
        rootId = ast.root.id ?? "";
        const resp = await api.post("/api/v1/conversations/step-counts", {
          data: { siteId, strategyAst: { recordType: ast.recordType, root: ast.root } },
          headers: CSRF_HEADERS,
          timeout: 120_000,
        });
        if (!resp.ok()) {
          return `step-counts ${resp.status()} on record type "${ast.recordType}": ${await resp.text()}`;
        }
        counts = ((await resp.json()) as StepCountsResponse).counts;
        return typeof counts[rootId] === "number"
          ? "counted"
          : `no count for ${rootId}`;
      },
      { timeout: 120_000, intervals: [2_000, 5_000, 10_000] },
    )
    .toBe("counted");
  const root = counts[rootId];
  if (typeof root !== "number")
    throw new Error(`the site answered no count for ${rootId}`);
  return { root, byStep: counts };
}

/** A count as the app prints it, `1,203`. */
export function printed(count: number): string {
  return count.toLocaleString("en-US");
}

/** A count in prose, with or without the thousands separator. */
export function countPattern(count: number): RegExp {
  const forms = [String(count), printed(count)].join("|");
  return new RegExp(`(^|[^\\d,])(${forms})([^\\d,]|$)`);
}

/** The caption the `Strategy updated` figure writes. */
export function strategyCaption(steps: number, genes: number): string {
  return `${printed(steps)} ${steps === 1 ? "step" : "steps"}, ${printed(genes)} genes`;
}

/** The site's row in the api's site list. */
export async function siteRow(api: ApiClient, siteId: string): Promise<SiteResponse> {
  const resp = await api.get("/api/v1/sites");
  expect(resp.status()).toBe(200);
  const site = ((await resp.json()) as SiteResponse[]).find((row) => row.id === siteId);
  if (site === undefined) throw new Error(`the api lists no site ${siteId}`);
  return site;
}

interface SeedControlSet {
  name: string;
  positive_ids: string[];
  negative_ids: string[];
}

interface SeedEntry {
  name: string;
  control_set?: SeedControlSet | null;
  step_tree?: unknown;
}

const SEEDS_DIR = path.resolve("../api/src/pathfinder/data/seeds");

function seedsOf(siteId: string): SeedEntry[] {
  const file = path.join(SEEDS_DIR, `${siteId}.json`);
  return JSON.parse(fs.readFileSync(file, "utf8")) as SeedEntry[];
}

function organismValues(value: unknown): string[] {
  if (typeof value !== "string") return [];
  if (!value.startsWith("[")) return [value];
  const parsed: unknown = JSON.parse(value);
  return Array.isArray(parsed) ? parsed.filter((v) => typeof v === "string") : [];
}

function collectOrganisms(node: unknown, out: string[]): void {
  if (Array.isArray(node)) {
    for (const child of node) collectOrganisms(child, out);
    return;
  }
  if (node === null || typeof node !== "object") return;
  for (const [key, value] of Object.entries(node)) {
    if (key.endsWith("organism")) out.push(...organismValues(value));
    collectOrganisms(value, out);
  }
}

/** The organism most of the site's seed parameters name: the site's own organism. */
export function siteOrganism(siteId: string): string {
  const values: string[] = [];
  collectOrganisms(seedsOf(siteId), values);
  const tally = new Map<string, number>();
  for (const value of values) tally.set(value, (tally.get(value) ?? 0) + 1);
  const [top] = [...tally].sort((a, b) => b[1] - a[1]);
  if (top === undefined) throw new Error(`the ${siteId} seeds name no organism`);
  return top[0];
}

/** The control sets the site's seeds carry. */
export function siteControlSets(siteId: string): SeedControlSet[] {
  return seedsOf(siteId)
    .map((seed) => seed.control_set)
    .filter((set): set is SeedControlSet => set != null);
}

/** The prefix of the site's gene ids, such as `PF3D7_` or `AGAP`, read from its seed controls. */
export function siteGeneIdPrefix(siteId: string): string {
  const [first] = siteControlSets(siteId).flatMap((set) => set.positive_ids);
  if (first === undefined) throw new Error(`the ${siteId} seeds carry no control ids`);
  const underscore = first.indexOf("_");
  return underscore >= 0
    ? first.slice(0, underscore + 1)
    : (/^[A-Za-z]+/.exec(first)?.[0] ?? "");
}
