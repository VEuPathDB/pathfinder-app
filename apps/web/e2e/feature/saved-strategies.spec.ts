/**
 * Deleting a saved strategy from the saved-strategies page: the delete waits
 * for the confirm, names the site, and removes only the site's strategy.
 */

import type { Request } from "@playwright/test";
import { type ConversationResponse, siteShortName } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api-client";
import { SIGNAL_PEPTIDE } from "../fixtures/arc-layouts";
import { siteOrganism } from "../fixtures/site-reads";

/** A saved, site-linked conversation made through the API, returned by id. */
async function makeSaved(
  api: ApiClient,
  siteId: string,
  name: string,
): Promise<string> {
  const created = await api.post("/api/v1/conversations", {
    data: {
      name,
      siteId,
      strategyAst: {
        recordType: "transcript",
        root: {
          id: "root",
          searchName: SIGNAL_PEPTIDE,
          parameters: {
            organism: { type: "string", value: siteOrganism(siteId) },
          },
        },
      },
    },
  });
  expect(created.status()).toBe(201);
  const id = ((await created.json()) as ConversationResponse).id;
  const uniqueWdkId = Math.floor(Date.now() / 1000) + Math.floor(Math.random() * 10000);
  const patched = await api.patch(`/api/v1/conversations/${id}`, {
    data: { isSaved: true, wdkStrategyId: uniqueWdkId },
  });
  expect(patched.status()).toBe(200);
  return id;
}

function isDeleteOf(id: string) {
  return (request: Request) =>
    request.method() === "DELETE" && request.url().includes(`/conversations/${id}`);
}

test.describe("Saved strategies", () => {
  test("a delete waits for the confirm and names the site", async ({
    page,
    chatPage,
    apiClient,
    siteId,
  }) => {
    await apiClient.delete("/api/v1/user/data?deleteWdk=true");
    await chatPage.goto();
    const id = await makeSaved(apiClient, siteId, "Kinase sweep");
    const deletes: string[] = [];
    page.on("request", (request) => {
      if (isDeleteOf(id)(request)) deletes.push(request.url());
    });

    await page.goto(`/${siteId}/saved`);
    const row = page.getByTestId(`saved-strategy-${id}`);
    await expect(row).toBeVisible({ timeout: 15_000 });

    await page.getByTestId(`saved-strategy-delete-${id}`).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText(
      `This also deletes the strategy on ${siteShortName(siteId)}, and PathFinder cannot restore it.`,
    );
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(row).toBeVisible();
    expect(deletes).toEqual([]);

    await page.getByTestId(`saved-strategy-delete-${id}`).click();
    const sent = page.waitForRequest(isDeleteOf(id));
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
    const url = new URL((await sent).url());
    expect(url.searchParams.get("deleteFromWdk")).toBe("true");
    // The dialog names only the site's strategy, so a branch of it stays.
    expect(url.searchParams.get("cascade")).toBeNull();
    await expect(row).toHaveCount(0, { timeout: 10_000 });
  });
});
