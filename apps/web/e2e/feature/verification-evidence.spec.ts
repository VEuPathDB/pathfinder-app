import type { SiteResponse } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api-client";
import { MOCK_CONTROLS_PROMPT } from "../fixtures/mock-prompts";
import { currentSiteId } from "../pages/navigation";

/** The evidence card a check leaves, under the check and in the rail. The mock
 * VERIFY tests the taxon search with three P. falciparum genes and one Toxoplasma
 * gene on the real site, then reads two sampled records; only the LLM is mocked. */

const POSITIVES = "PF3D7_0102600, PF3D7_0709000, PF3D7_1133400";
const NEGATIVE = "TGME49_205250";
const ORGANISM = "Plasmodium falciparum 3D7";

/** The thread's site as the api lists it. */
async function siteOf(apiClient: ApiClient, siteId: string): Promise<SiteResponse> {
  const response = await apiClient.get("/api/v1/sites");
  expect(response.ok()).toBeTruthy();
  const sites = (await response.json()) as SiteResponse[];
  const site = sites.find((s) => s.id === siteId);
  if (site === undefined) throw new Error(`the api lists no site ${siteId}`);
  return site;
}

/** The step page the card links: the thread's site, one strategy and one step. */
function strategyLinkOf(site: SiteResponse): RegExp {
  const web = site.baseUrl.replace(/\/service$/, "");
  const escaped = web.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${escaped}/app/workspace/strategies/\\d+/\\d+$`);
}

test.describe("Verification evidence", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("the check leaves a card with every control id, in the thread and the rail", async ({
    chatPage,
    page,
    apiClient,
  }) => {
    await chatPage.send(MOCK_CONTROLS_PROMPT);
    await chatPage.expectVerificationSuccess();
    await chatPage.expectIdle();

    const card = page.getByTestId("data-evidence-card");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("evidence-ids-positive-returned")).toHaveText(
      POSITIVES,
    );
    await expect(card.getByTestId("evidence-ids-negative-not-returned")).toHaveText(
      NEGATIVE,
    );
    const site = await siteOf(apiClient, currentSiteId(page));
    const strategyLink = card.getByTestId("evidence-strategy-link");
    await expect(strategyLink).toHaveAttribute("href", strategyLinkOf(site));
    await expect(strategyLink).toHaveText(`Open in ${site.name}`);

    const requirements = card.getByTestId("evidence-requirements");
    const organismRow = requirements.getByRole("row", { name: new RegExp(ORGANISM) });
    await expect(organismRow.getByTestId("evidence-requirement-status")).toHaveText(
      "Met",
    );
    await expect(
      organismRow.getByRole("cell", { name: "by a parameter" }),
    ).toBeVisible();
    await expect(card.getByTestId("evidence-sample-count")).toHaveText(
      "2 of 2 sampled genes fit",
    );
    await expect(
      card
        .getByTestId("evidence-sampled-genes")
        .getByRole("cell", { name: /^PF3D7_\d{7}$/ }),
    ).toHaveCount(2);

    await page.getByRole("button", { name: "Open Progress" }).click();
    await page.getByRole("button", { name: /^Checking/ }).click();
    const rail = page.getByTestId("ledger-panel");
    await expect(rail.getByTestId("evidence-ids-positive-returned")).toHaveText(
      POSITIVES,
    );
    await expect(rail.getByTestId("evidence-ids-negative-not-returned")).toHaveText(
      NEGATIVE,
    );
  });
});
