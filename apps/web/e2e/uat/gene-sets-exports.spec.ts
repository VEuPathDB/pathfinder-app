/**
 * UAT flows G1 to G4: a gene set saved from a strategy, exported, published to
 * the VEuPathDB workspace, and imported from pasted ids. Counts and ids are
 * read from the site and the api; only the model is mocked.
 */

import type { Locator, Page } from "@playwright/test";
import {
  type GeneSet,
  type VdiPublicationStatus,
  siteShortName,
} from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import type { ApiClient } from "../fixtures/api-client";
import { expectEvidence, openTrace, traceRows } from "../fixtures/build-checks";
import {
  buildIntersect,
  downloadedText,
  exportFile,
  exportedIds,
  geneSetsOf,
  importGeneIds,
  seedGeneIds,
  toast,
} from "../fixtures/composer";
import {
  countPattern,
  printed,
  readConversation,
  siteGeneIdPrefix,
} from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";

const DELETE_NOTICE =
  "PathFinder removes this gene set and cannot restore it. A dataset published from it stays in your VEuPathDB workspace.";

/** Ask for the strategy's genes as a gene set named `name`; returns its figure. */
async function saveGeneSet(
  page: Page,
  chatPage: ChatPage,
  name: string,
): Promise<Locator> {
  await chatPage.sendAndSettle(
    prompt(
      "save-gene-set",
      `Save the genes of this strategy as a gene set named ${name}.`,
    ),
  );
  const figure = page.getByTestId("data-gene-set").filter({ hasText: name });
  await expect(figure).toHaveCount(1, { timeout: 60_000 });
  return figure;
}

/** The api's gene set named `name` on the site. */
async function savedSet(
  api: ApiClient,
  siteId: string,
  name: string,
): Promise<GeneSet> {
  const set = (await geneSetsOf(api, siteId)).find((row) => row.name === name);
  if (set === undefined) throw new Error(`the api lists no gene set ${name}`);
  return set;
}

async function publication(
  api: ApiClient,
  geneSetId: string,
): Promise<VdiPublicationStatus> {
  const resp = await api.get(`/api/v1/gene-sets/${geneSetId}/vdi-publication`);
  expect(resp.status(), `publication of ${geneSetId}`).toBe(200);
  return (await resp.json()) as VdiPublicationStatus;
}

function literal(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test.describe("Gene sets from a strategy", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("G1 - Save a gene set from a strategy", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    const name = "UAT G1";
    const { counts } = await buildIntersect(page, chatPage, apiClient, siteId);
    const figure = await saveGeneSet(page, chatPage, name);

    await expect(figure.locator("figcaption")).toHaveText(name);
    await expect(figure.getByTestId("figure-caption")).toHaveText(
      `${printed(counts.root)} genes on ${siteShortName(siteId)}`,
    );
    await expect(figure).toContainText("Gene set created");
    const publish = figure.getByRole("button", {
      name: "Publish to VEuPathDB workspace",
    });
    await expect(publish).toBeVisible();
    const remove = figure.getByRole("button", { name: "Delete gene set" });
    await expect(remove).toHaveText("Delete");

    const set = await savedSet(apiClient, siteId, name);
    expect(set.geneCount).toBe(counts.root);
    expect(set.source).toBe("strategy");

    const reply = chatPage.assistantMessages.filter({
      has: page.getByTestId("data-gene-set"),
    });
    await expect(
      reply.locator(".prose").filter({ hasText: countPattern(counts.root) }),
    ).not.toHaveCount(0);
    await openTrace(reply);
    await expect(traceRows(reply, "Save gene set")).toHaveCount(1);

    await remove.click();
    const confirm = page.getByRole("alertdialog", { name: `Delete ${name}?` });
    await expect(confirm).toContainText(DELETE_NOTICE);
    await confirm.getByRole("button", { name: "Delete" }).click();
    await expect(figure).toContainText("Gene set deleted");
    await expect(figure.getByRole("button")).toHaveCount(0);
    expect((await geneSetsOf(apiClient, siteId)).map((row) => row.name)).not.toContain(
      name,
    );
  });

  test("G2 - Export the gene set and the strategy", async ({
    page,
    chatPage,
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { id, counts } = await buildIntersect(page, chatPage, apiClient, siteId);
    await saveGeneSet(page, chatPage, "UAT G2");
    const set = await savedSet(apiClient, siteId, "UAT G2");

    for (const format of ["csv", "txt"]) {
      const file = await exportFile(page, chatPage, `gene-set-${format}`);
      expect(file.suggestedFilename()).toMatch(new RegExp(`\\.${format}$`));
      const ids = exportedIds(await downloadedText(file));
      expect(ids).toEqual(set.geneIds);
      expect(ids).toHaveLength(counts.root);
      expect(ids.filter((gene) => !gene.startsWith(siteGeneIdPrefix(siteId)))).toEqual(
        [],
      );
    }

    const site = siteShortName(siteId);
    const url = (await readConversation(apiClient, id)).wdkUrl ?? "";
    expect(url).toMatch(/\/app\/workspace\/strategies\/\d+$/);
    const card = await expectEvidence(page, "Supported", counts.root);
    await expect(
      card.getByRole("link", { name: `Run GO, pathway or word enrichment in ${site}` }),
    ).toHaveAttribute("href", new RegExp(`^${literal(url)}(/\\d+)?$`));

    await graphPage.openRailStrategyPanel();
    const railLink = page.getByTestId("rail-strategy-wdk-link");
    await expect(railLink).toHaveText(site);
    await expect(railLink).toHaveAttribute("href", url);
  });
});

// Publishing writes a dataset to the account's workspace, so it runs once, on plasmodb.
test.describe("Publishing a gene set", { tag: "@named-site" }, () => {
  test("G3 - Publish to the VEuPathDB workspace", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    test.setTimeout(900_000);
    const { counts } = await buildIntersect(page, chatPage, apiClient, siteId);
    const figure = await saveGeneSet(page, chatPage, "UAT G3");
    const set = await savedSet(apiClient, siteId, "UAT G3");

    await figure
      .getByRole("button", { name: "Publish to VEuPathDB workspace" })
      .click();
    const visibility = figure.getByLabel("Visibility");
    await expect(visibility).toHaveValue("private");
    await expect(visibility.locator("option")).toHaveText([
      "private",
      "protected",
      "public",
    ]);
    await visibility.selectOption("private");
    await expect(figure.getByRole("button", { name: "Cancel" })).toBeVisible();
    await figure.getByRole("button", { name: "Confirm publish" }).click();

    await expect(toast(page, `Published ${printed(counts.root)} genes`)).toBeVisible({
      timeout: 120_000,
    });
    await expect(figure).toContainText(
      new RegExp(`Installed on ([^,]+, )*${literal(siteShortName(siteId))}`),
      { timeout: 600_000 },
    );
    const status = await publication(apiClient, set.id);
    expect(status.installed).toBe(true);
    await expect(figure.getByRole("link", { name: "Open dataset" })).toHaveAttribute(
      "href",
      status.datasetUrl,
    );
  });
});

test.describe("Gene sets from pasted ids", () => {
  test("G4 - Import a gene set from pasted ids", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    const ids = seedGeneIds(siteId, 3);
    await chatPage.startOn(siteId);
    await importGeneIds(page, chatPage, "UAT import G4", ids.join("\n"));
    await expect
      .poll(async () => (await geneSetsOf(apiClient, siteId)).map((set) => set.name))
      .toEqual(["UAT import G4"]);

    for (const format of ["csv", "txt"]) {
      const file = await exportFile(page, chatPage, `gene-set-${format}`);
      expect(exportedIds(await downloadedText(file))).toEqual(ids);
    }
  });
});
