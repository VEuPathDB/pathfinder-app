/**
 * UAT flows X1 to X6: one request on two sites, each site's own searches
 * first, and orthology on the component sites and across genera on the
 * portal. Every test names the sites it runs on; counts are read from the site.
 */

import type { Locator, Page } from "@playwright/test";
import { siteShortName, type GeneSet, type Search } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { type ApiClient, listBody } from "../fixtures/api-client";
import { type AstNode, COMBINE_SEARCH_NAME } from "../fixtures/ast";
import { LAYOUTS, ORTHOLOGS, layoutOf } from "../fixtures/arc-layouts";
import {
  expectBuild,
  expectEvidence,
  openTrace,
  sampledGeneIds,
  traceRows,
} from "../fixtures/build-checks";
import {
  countPattern,
  readNodes,
  type SiteCounts,
  siteGeneIdPrefix,
  siteOrganism,
  storedNodes,
} from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";
import type { GraphPage } from "../pages/graph.page";

const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;
const X1_TEXT = "Which genes are upregulated in female mosquitoes after a blood meal?";
const X1_SET = "UAT X1 blood meal";
const ORTHOLOGS_TEXT = "Carry these to their orthologs in the related species.";
const SYNTENIC_TEXT = "Carry these to their syntenic orthologs in the related genus.";

/** The two sites X2 compares: the two `E2E_SITES` names, else plasmodb and vectorbase. */
function comparedSites(): string[] {
  const listed = (process.env["E2E_SITES"] ?? "")
    .split(",")
    .map((site) => site.trim())
    .filter((site) => site !== "");
  return listed.length >= 2 ? listed : ["plasmodb", "vectorbase"];
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

/** The ids of every site the api serves. */
async function servedSites(api: ApiClient): Promise<string[]> {
  const rows = await listBody<{ id: string }>(await api.get("/api/v1/sites"), "sites");
  return rows.map((row) => row.id);
}

async function geneSetsOn(api: ApiClient, siteId: string): Promise<GeneSet[]> {
  return listBody(await api.get(`/api/v1/gene-sets?siteId=${siteId}`), "gene sets");
}

/** Open a fresh conversation on `siteId`, send `message` and return the id. */
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

/** The S2 build on `siteId`, with the counts the site answers for it. */
async function buildS2(
  chatPage: ChatPage,
  api: ApiClient,
  page: Page,
  siteId: string,
): Promise<{ id: string; counts: SiteCounts }> {
  const id = await sendOn(
    chatPage,
    siteId,
    prompt("intersect", S2_TEXT(siteOrganism(siteId))),
  );
  const counts = await expectBuild(page, api, id, siteId, LAYOUTS.intersect);
  return { id, counts };
}

/** Every search the stored tree runs is one the site itself lists. */
async function expectOwnSearches(api: ApiClient, siteId: string, id: string) {
  const resp = await api.get(`/api/v1/sites/${siteId}/searches`);
  expect(resp.status()).toBe(200);
  const own = new Set(((await resp.json()) as Search[]).map((search) => search.name));
  const leaves = (await readNodes(api, id))
    .filter((node) => node.searchName !== COMBINE_SEARCH_NAME)
    .map((node) => node.searchName ?? "");
  expect(leaves).not.toEqual([]);
  expect(leaves.filter((name) => !own.has(name))).toEqual([]);
}

/**
 * The `Find searches` rows count the site's own searches, and label another
 * site's experiments by that site's id, never by this one.
 */
async function expectFindSearches(reply: Locator, siteId: string, served: string[]) {
  await openTrace(reply);
  const summaries = traceRows(reply, "Find searches").getByTestId("trace-row-summary");
  await expect(summaries).not.toHaveCount(0);
  for (const summary of await summaries.allTextContents()) {
    const match = /^[\d,]+ searches(?:, experiments on (.+))?$/.exec(summary.trim());
    expect(match, `Find searches reads "${summary}"`).not.toBe(null);
    const named = (match?.[1] ?? "").split(/, | and /).filter((name) => name !== "");
    expect(named).not.toContain(siteId);
    for (const other of named) expect(served).toContain(other);
  }
}

/** The transform a build left, carried to another organism without synteny. */
async function expectOrthologs(
  chatPage: ChatPage,
  graphPage: GraphPage,
  api: ApiClient,
  page: Page,
  siteId: string,
  id: string,
) {
  await chatPage.sendAndSettle(prompt("orthologs", ORTHOLOGS_TEXT));
  const counts = await expectBuild(page, api, id, siteId, LAYOUTS.orthologs);
  const transform = nodeBySearch(await readNodes(api, id), ORTHOLOGS);
  expect(paramText(transform, "isSyntenic")).toBe("no");
  expect(paramText(transform, "organism")).not.toBe("");
  expect(paramText(transform, "organism")).not.toContain(siteOrganism(siteId));
  await expect(chatPage.assistantReply(countPattern(counts.root))).not.toHaveCount(0);

  const card = await expectEvidence(page, /Supported|Not supported/, counts.root);
  const genes = await sampledGeneIds(card);
  expect(genes.length).toBeGreaterThan(0);
  for (const gene of genes)
    expect(gene.startsWith(siteGeneIdPrefix(siteId))).toBe(false);

  await graphPage.goToStrategy(siteId, id);
  await graphPage.expectStrategyTopbar();
  await graphPage.clickNode(transform.id ?? "");
  await graphPage.expectEditorSheetOpen();
  await expect(graphPage.editorSheet).toContainText("Syntenic Orthologs Only?");
  await page.goto(`/${siteId}/conversation/${id}`);
  await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
}

test.describe("Cross-site and orthology", { tag: "@named-site" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("X1 - The same request on plasmodb and vectorbase", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    test.setTimeout(900_000);
    const served = await servedSites(apiClient);
    const id = await sendOn(
      chatPage,
      "vectorbase",
      prompt("other-site-experiment", X1_TEXT),
    );
    await expect
      .poll(async () => (await storedNodes(apiClient, id)).length, { timeout: 60_000 })
      .toBeGreaterThan(0);
    const layout = layoutOf(await readNodes(apiClient, id));
    const counts = await expectBuild(page, apiClient, id, "vectorbase", layout);
    await expectOwnSearches(apiClient, "vectorbase", id);
    const reply = chatPage.assistantReply(countPattern(counts.root));
    await expect(reply).not.toHaveCount(0);
    await expectFindSearches(reply, "vectorbase", served);

    await chatPage.sendAndSettle(
      prompt(
        "save-gene-set",
        `Save the genes of this strategy as a gene set named ${X1_SET}.`,
      ),
    );
    await expect(
      page.getByTestId("data-gene-set").filter({ hasText: X1_SET }),
    ).toBeVisible({ timeout: 60_000 });
    const saved = (await geneSetsOn(apiClient, "vectorbase")).find(
      (set) => set.name === X1_SET,
    );
    expect(saved?.siteId).toBe("vectorbase");
    expect(saved?.geneCount).toBe(counts.root);
    // Which vector the bound experiment covers is the model's pick; the mock
    // stack holds that the genes are VectorBase's, never another site's.
    const foreign = siteGeneIdPrefix("plasmodb");
    expect((saved?.geneIds ?? []).filter((gene) => gene.startsWith(foreign))).toEqual(
      [],
    );
    expect(saved?.geneIds.length).toBe(counts.root);

    const elsewhere = await sendOn(
      chatPage,
      "plasmodb",
      prompt("other-site-experiment", X1_TEXT),
    );
    // Whether PlasmoDB binds a search of its own is the model's call; the mock
    // stack holds that no step runs a search PlasmoDB does not list.
    const listed = await apiClient.get("/api/v1/sites/plasmodb/searches");
    expect(listed.status()).toBe(200);
    const own = new Set(
      ((await listed.json()) as Search[]).map((search) => search.name),
    );
    const bound = (await storedNodes(apiClient, elsewhere))
      .filter((node) => node.searchName !== COMBINE_SEARCH_NAME)
      .map((node) => node.searchName ?? "");
    expect(bound.filter((name) => !own.has(name))).toEqual([]);
    await expectFindSearches(chatPage.assistantMessages, "plasmodb", served);

    const plasmoSets = await geneSetsOn(apiClient, "plasmodb");
    expect(plasmoSets.map((set) => set.id)).not.toContain(saved?.id);
    const again = (await geneSetsOn(apiClient, "vectorbase")).find(
      (set) => set.id === saved?.id,
    );
    expect(again?.geneCount).toBe(counts.root);
  });

  test("X2 - Own-site searches first, other sites labelled", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    test.setTimeout(900_000);
    const served = await servedSites(apiClient);
    for (const siteId of comparedSites()) {
      const { id, counts } = await buildS2(chatPage, apiClient, page, siteId);
      await expectOwnSearches(apiClient, siteId, id);
      const reply = chatPage.assistantReply(countPattern(counts.root));
      await expectFindSearches(reply, siteId, served);
    }
  });

  test("X3 - Orthology on vectorbase and toxodb", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
  }) => {
    test.setTimeout(1_200_000);
    const served = await servedSites(apiClient);
    const sites = ["vectorbase", "toxodb"].filter((site) => served.includes(site));
    expect(sites).toContain("vectorbase");
    for (const siteId of sites) {
      const { id } = await buildS2(chatPage, apiClient, page, siteId);
      await expectOrthologs(chatPage, graphPage, apiClient, page, siteId, id);
    }
  });

  test("X4 - Orthology on fungidb", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
  }) => {
    const { id } = await buildS2(chatPage, apiClient, page, "fungidb");
    await expectOrthologs(chatPage, graphPage, apiClient, page, "fungidb", id);
  });

  test("X5 - Across genera on the portal", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
  }) => {
    test.setTimeout(900_000);
    const portal = "veupathdb";
    const { id, counts } = await buildS2(chatPage, apiClient, page, portal);

    const branch = await chatPage.branchFromAssistantReply(countPattern(counts.root));
    await chatPage.sendAndSettle(prompt("syntenic-orthologs", SYNTENIC_TEXT));
    const empty = await expectBuild(page, apiClient, branch, portal, LAYOUTS.orthologs);
    expect(empty.root).toBe(0);
    const syntenic = nodeBySearch(await readNodes(apiClient, branch), ORTHOLOGS);
    expect(paramText(syntenic, "isSyntenic")).toBe("yes");
    const refused = page.getByTestId("data-evidence-card").filter({
      has: page.getByTestId("evidence-verdict").filter({ hasText: "Not supported" }),
    });
    await expect(refused).not.toHaveCount(0, { timeout: 60_000 });
    await expect(chatPage.assistantReply(countPattern(0))).not.toHaveCount(0);

    await page.goto(`/${portal}/conversation/${id}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    await expectOrthologs(chatPage, graphPage, apiClient, page, portal, id);
  });

  test("X6 - An organism the site's sheet does not reach", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    test.setTimeout(900_000);
    const cases = [
      { siteId: "vectorbase", target: siteOrganism("plasmodb") },
      { siteId: "plasmodb", target: siteOrganism("toxodb") },
    ];
    for (const { siteId, target } of cases) {
      const { id } = await buildS2(chatPage, apiClient, page, siteId);
      await chatPage.sendAndSettle(
        prompt("portal-only", `Carry these to their orthologs in ${target}.`),
      );
      expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.intersect);
      await expect(
        chatPage.assistantReply(new RegExp(siteShortName("veupathdb"))),
      ).not.toHaveCount(0);
    }
  });
});
