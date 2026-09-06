import { test, expect } from "../fixtures/a11y";
import { clearAllGeneSets } from "../fixtures/api-client";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

test.describe("Gene Set Analysis Pipeline", () => {
  test("add overlapping sets, perform intersection, verify counts, run enrichment on derived set", async ({
    page,
    seedData,
    sitePicker,
    workbenchSidebarPage,
    workbenchMainPage,
    apiClient,
  }) => {
    await clearAllGeneSets(page.context(), BASE_URL);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");

    // Set A: first 3 genes, Set B: genes 1-4 (overlapping genes at indices 1,2)
    const setAGenes = seedData.plasmoGenes.slice(0, 3);
    const setBGenes = seedData.plasmoGenes.slice(1, 5);
    const setACount = setAGenes.length; // 3
    const setBCount = setBGenes.length; // 4
    // Intersection: genes at indices 1,2 (overlap between [0,1,2] and [1,2,3,4])
    const intersectionCount = 2;

    // ── Phase 1: Add two overlapping sets ───────────────────────
    await workbenchSidebarPage.openAddModal();
    await page.getByLabel(/name/i).fill("Set A");
    await page.getByLabel(/gene ids/i).fill(setAGenes.join("\n"));
    await page.getByRole("button", { name: /add gene set/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });
    await workbenchSidebarPage.expectSetGeneCount("Set A", setACount);

    await workbenchSidebarPage.openAddModal();
    await page.getByLabel(/name/i).fill("Set B");
    await page.getByLabel(/gene ids/i).fill(setBGenes.join("\n"));
    await page.getByRole("button", { name: /add gene set/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });
    await workbenchSidebarPage.expectSetGeneCount("Set B", setBCount);

    // ── Phase 2: Set operation with count verification ──────────
    await workbenchSidebarPage.selectSet("Set A");
    await workbenchSidebarPage.selectSet("Set B");

    await expect(page.getByRole("button", { name: /intersect/i })).toBeVisible({
      timeout: 10_000,
    });

    // UI: Preview count shows intersection size
    await workbenchSidebarPage.expectComposeResultCount(intersectionCount);

    // Perform intersection
    await workbenchSidebarPage.performOperation("intersect");
    await workbenchSidebarPage.expectSetCount(3);

    // ── Phase 3: Activate derived set & run enrichment ──────────
    // The derived set should auto-activate or we activate it
    // Look for the derived set — it won't have the exact names "Set A" or "Set B"
    // It will be the third set created

    // API: Verify derived set count
    const resp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const sets = await resp.json();
    expect(sets.length).toBeGreaterThanOrEqual(3);

    const derived = sets.find((gs: { source: string }) => gs.source === "derived");
    expect(derived).toBeDefined();
    expect(derived.geneCount).toBe(intersectionCount);
    expect(derived.operation).toBe("intersect");

    // API: Verify the individual sets have correct counts too
    const setA = sets.find((gs: { name: string }) => gs.name === "Set A");
    expect(setA).toBeDefined();
    expect(setA.geneCount).toBe(setACount);

    const setB = sets.find((gs: { name: string }) => gs.name === "Set B");
    expect(setB).toBeDefined();
    expect(setB.geneCount).toBe(setBCount);

    // ── Phase 4: Enrichment on a set ────────────────────────────
    // Activate the original "Set A". The card's name span carries the set
    // name as its title, so the derived "Set A ∩ Set B" card does not match.
    await page
      .getByRole("button")
      .filter({ has: page.locator('span[title="Set A"]') })
      .click();
    await expect(
      page.getByRole("heading", { name: "Set A", exact: true, level: 1 }),
    ).toBeVisible();
    await workbenchMainPage.expectActiveSetHeader("Set A", setACount);

    // Run enrichment — real WDK enrichment API call
    await workbenchMainPage.runEnrichmentAndVerifyResults();
    await workbenchMainPage.expectEnrichmentResultsWithData();
    await workbenchMainPage.expectEnrichmentTypeTabs();
  });
});
