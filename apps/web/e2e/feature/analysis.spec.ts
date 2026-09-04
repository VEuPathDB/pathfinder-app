import { test, expect } from "../fixtures/test";
import type { WorkbenchSidebarPage } from "../pages/workbench-sidebar.page";
import type { Page } from "@playwright/test";

async function addAndActivateGeneSet(
  page: Page,
  workbenchSidebarPage: WorkbenchSidebarPage,
  name: string,
  geneIds: string[],
) {
  await workbenchSidebarPage.openAddModal();
  await page.getByLabel(/name/i).fill(name);
  await page.getByLabel(/gene ids/i).fill(geneIds.join("\n"));
  await page.getByRole("button", { name: /add gene set/i }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });
  await workbenchSidebarPage.activateSet(name);
}

test.describe("Analysis Panels", () => {
  test.beforeEach(async ({ page, sitePicker }) => {
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");
  });

  test("enrichment runs and returns real WDK results", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
    apiClient,
  }) => {
    const genes = seedData.plasmoGenes;
    await addAndActivateGeneSet(page, workbenchSidebarPage, "Enrichment Test", genes);

    // UI: Active set header shows correct count
    await workbenchMainPage.expectActiveSetHeader("Enrichment Test", genes.length);

    // UI: Run enrichment via click
    await workbenchMainPage.runEnrichmentAndVerifyResults();

    // UI: Results contain real data with numbers
    await workbenchMainPage.expectEnrichmentResultsWithData();

    // UI: Enrichment type tabs visible (GO:BP, GO:MF, etc.)
    await workbenchMainPage.expectEnrichmentTypeTabs();

    // API: Verify gene set exists with correct data
    const resp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const sets = await resp.json();
    const testSet = sets.find((gs: { name: string }) => gs.name === "Enrichment Test");
    expect(testSet).toBeDefined();
    expect(testSet.geneCount).toBe(genes.length);
  });

  test("strategy-only panels show disabled reason for paste sets", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    await addAndActivateGeneSet(
      page,
      workbenchSidebarPage,
      "Paste Set",
      seedData.plasmoGenes,
    );

    // UI: Active set header shows count
    await workbenchMainPage.expectActiveSetHeader(
      "Paste Set",
      seedData.plasmoGenes.length,
    );

    // UI: Results Table and Distribution Explorer require strategy-backed sets
    await expect(
      page
        .getByRole("button", { expanded: false })
        .filter({ hasText: /results table/i })
        .filter({ hasText: /requires.*strategy/i }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("button", { expanded: false })
        .filter({ hasText: /distribution explorer/i })
        .filter({ hasText: /requires.*strategy/i }),
    ).toBeVisible();
  });

  test("all analysis panels are listed", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    await addAndActivateGeneSet(
      page,
      workbenchSidebarPage,
      "Panel Check",
      seedData.plasmoGenes.slice(0, 3),
    );

    const panelTitles = [
      "Evaluate",
      "Batch (multi-organism)",
      "Benchmark (multi-control-set)",
      "Results Table",
      "Enrichment Analysis",
      "Distribution Explorer",
      "Gene Confidence",
      "Ensemble Scoring",
      "Reverse Search",
      "Custom Enrichment",
      "Parameter Sweep",
    ];

    // UI: All panels visible
    for (const title of panelTitles) {
      await workbenchMainPage.expectPanelVisible(title);
    }
  });
});
