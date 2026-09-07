import { test, expect } from "../fixtures/test";
import { clearAllGeneSets } from "../fixtures/api-client";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

interface SiteRow {
  id: string;
  isPortal: boolean;
  available: boolean;
}

/** The site the entry flow opens: the portal when it answers, else the first
 *  site the API reports available, in the list's own order. */
function entrySite(sites: SiteRow[]): SiteRow {
  const available = sites.filter((s) => s.available);
  const entry = available.find((s) => s.isPortal) ?? available[0];
  if (entry === undefined) throw new Error("the API reports no available site");
  return entry;
}

test.describe("Site Switching", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("the default site is the one the API reports available", async ({
    sitePicker,
    apiClient,
  }) => {
    const resp = await apiClient.get("/api/v1/sites");
    expect(resp.ok()).toBeTruthy();
    const sites = (await resp.json()) as SiteRow[];
    expect(sites.length).toBeGreaterThan(0);
    const siteIds = sites.map((s) => s.id);
    expect(siteIds).toContain("plasmodb");
    expect(siteIds).toContain("toxodb");
    expect(siteIds).toContain("cryptodb");

    await sitePicker.expectCurrentSite(entrySite(sites).id);
  });

  test("switch site updates UI and isolates gene sets per site", async ({
    sitePicker,
    page,
    seedData,
    workbenchSidebarPage,
    apiClient,
  }) => {
    // Clear gene sets for both sites
    await clearAllGeneSets(page.context(), BASE_URL);

    // Add a gene set on PlasmoDB
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");
    await workbenchSidebarPage.openAddModal();
    await page.getByLabel(/name/i).fill("PlasmoDB Set");
    await page
      .getByLabel(/gene ids/i)
      .fill(seedData.plasmoGenes.slice(0, 2).join("\n"));
    await page.getByRole("button", { name: /add gene set/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });
    await workbenchSidebarPage.expectSetCount(1);

    // API: Verify PlasmoDB set exists (use name match — other workers may add sets)
    const plasmoResp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(plasmoResp.ok()).toBeTruthy();
    const plasmoSets = await plasmoResp.json();
    const ourSet = plasmoSets.find(
      (gs: { name: string }) => gs.name === "PlasmoDB Set",
    );
    expect(ourSet).toBeDefined();

    // UI: Switch to ToxoDB
    await page.goto("/");
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /switch database/i })).toBeVisible({
      timeout: 5_000,
    });
    await sitePicker.selectSite("toxodb");
    await sitePicker.expectCurrentSite("toxodb");

    // API: ToxoDB should have no gene sets (site isolation)
    const toxoResp = await apiClient.get("/api/v1/gene-sets?siteId=toxodb");
    expect(toxoResp.ok()).toBeTruthy();
    const toxoSets = await toxoResp.json();
    expect(toxoSets.length).toBe(0);

    // Switch back — PlasmoDB set still there
    await sitePicker.selectSite("plasmodb");
    await sitePicker.expectCurrentSite("plasmodb");

    const backResp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    const backSets = await backResp.json();
    const ourSetBack = backSets.find(
      (gs: { name: string }) => gs.name === "PlasmoDB Set",
    );
    expect(ourSetBack).toBeDefined();
  });
});
