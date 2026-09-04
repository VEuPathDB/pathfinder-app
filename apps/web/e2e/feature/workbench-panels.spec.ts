import { test, expect } from "../fixtures/test";
import type { WorkbenchSidebarPage } from "../pages/workbench-sidebar.page";
import type { Page } from "@playwright/test";
import { clearAllGeneSets } from "../fixtures/api-client";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

/**
 * Helper: create a gene set from pasted IDs, wait for the dialog to close,
 * and verify the card shows the expected count.
 */
async function addGeneSet(
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
  await workbenchSidebarPage.expectSetGeneCount(name, geneIds.length);
}

/**
 * Helper: create and immediately activate a gene set.
 */
async function addAndActivateGeneSet(
  page: Page,
  workbenchSidebarPage: WorkbenchSidebarPage,
  name: string,
  geneIds: string[],
) {
  await addGeneSet(page, workbenchSidebarPage, name, geneIds);
  await workbenchSidebarPage.activateSet(name);
}

test.describe("Workbench Panel Functionality", () => {
  test.beforeEach(async ({ page, sitePicker }) => {
    await clearAllGeneSets(page.context(), BASE_URL);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");
  });

  // ── Results Table (disabled for paste sets) ───────────────────────
  test("results table panel shows disabled reason for paste-based gene sets", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    const genes = seedData.plasmoGenes;
    await addAndActivateGeneSet(page, workbenchSidebarPage, "Paste Set", genes);

    // UI: Header shows name and count
    await workbenchMainPage.expectActiveSetHeader("Paste Set", genes.length);

    // UI: Results Table requires a strategy-backed gene set
    await expect(
      page
        .getByRole("button", { expanded: false })
        .filter({ hasText: /results table/i })
        .filter({ hasText: /requires.*strategy/i }),
    ).toBeVisible();

    // UI: Panel cannot be expanded — its toggle is disabled and stays collapsed.
    const panelBtn = page
      .getByRole("button", { expanded: false })
      .filter({ hasText: /results table/i });
    await expect(panelBtn).toBeDisabled();
  });

  // ── Enrichment Analysis ───────────────────────────────────────────
  test("enrichment runs and returns real results with p-values and type tabs", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    const genes = seedData.plasmoGenes;
    await addAndActivateGeneSet(
      page,
      workbenchSidebarPage,
      "Enrichment Panel Test",
      genes,
    );

    await workbenchMainPage.expectActiveSetHeader(
      "Enrichment Panel Test",
      genes.length,
    );

    // UI: Run enrichment and verify results
    await workbenchMainPage.runEnrichmentAndVerifyResults();

    // UI: Real data visible (significant terms, p-values in table)
    await workbenchMainPage.expectEnrichmentResultsWithData();

    // UI: Enrichment type tabs appear (GO:BP, GO:MF, etc.)
    await workbenchMainPage.expectEnrichmentTypeTabs();
  });

  test("enrichment panel shows Run Enrichment button when gene set is active", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    const genes = seedData.plasmoGenes.slice(0, 3);
    await addAndActivateGeneSet(
      page,
      workbenchSidebarPage,
      "Enrichment Btn Test",
      genes,
    );

    await workbenchMainPage.expectActiveSetHeader("Enrichment Btn Test", genes.length);

    // UI: Expand enrichment panel
    await workbenchMainPage.expandPanel("Enrichment Analysis");
    await workbenchMainPage.expectPanelExpanded("Enrichment Analysis");

    // UI: Run Enrichment button is visible
    await expect(page.getByRole("button", { name: /run enrichment/i })).toBeVisible();
  });

  // ── Distribution Explorer (disabled for paste sets) ───────────────
  test("distribution explorer shows disabled reason for paste-based gene sets", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    const genes = seedData.plasmoGenes;
    await addAndActivateGeneSet(page, workbenchSidebarPage, "Dist Test", genes);

    await workbenchMainPage.expectActiveSetHeader("Dist Test", genes.length);

    // UI: Distribution Explorer requires a strategy-backed gene set
    await expect(
      page
        .getByRole("button", { expanded: false })
        .filter({ hasText: /distribution explorer/i })
        .filter({ hasText: /requires.*strategy/i }),
    ).toBeVisible();
  });

  // ── Gene Set Operations: intersection ─────────────────────────────
  test("intersection of overlapping sets produces correct count", async ({
    page,
    seedData,
    workbenchSidebarPage,
    apiClient,
  }) => {
    const fullGenes = seedData.plasmoGenes;
    const subsetGenes = seedData.plasmoGenes.slice(0, 3);
    const intersectionCount = subsetGenes.length; // subset is contained in full

    await addGeneSet(page, workbenchSidebarPage, "Full Set", fullGenes);
    await addGeneSet(page, workbenchSidebarPage, "Subset", subsetGenes);

    // Select both sets
    await workbenchSidebarPage.selectSet("Full Set");
    await workbenchSidebarPage.selectSet("Subset");

    // UI: Compose bar shows intersection operation
    await expect(page.getByRole("button", { name: /intersect/i })).toBeVisible({
      timeout: 10_000,
    });

    // UI: Preview count shows intersection size
    await workbenchSidebarPage.expectComposeResultCount(intersectionCount);

    // Perform intersection
    await workbenchSidebarPage.performOperation("intersect");
    await workbenchSidebarPage.expectSetCount(3);

    // API: Derived set has correct count and operation
    const resp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const sets = await resp.json();
    const derived = sets.find((gs: { source: string }) => gs.source === "derived");
    expect(derived).toBeDefined();
    expect(derived.geneCount).toBe(intersectionCount);
    expect(derived.operation).toBe("intersect");
  });

  // ── Gene Set Operations: union ────────────────────────────────────
  test("union of overlapping sets produces correct count", async ({
    page,
    seedData,
    workbenchSidebarPage,
    apiClient,
  }) => {
    const setAGenes = seedData.plasmoGenes.slice(0, 3);
    const setBGenes = seedData.plasmoGenes.slice(1, 5);
    // Union: unique genes across both sets (indices 0,1,2,3,4 = 5 unique)
    const unionCount = new Set([...setAGenes, ...setBGenes]).size;

    await addGeneSet(page, workbenchSidebarPage, "Set A", setAGenes);
    await addGeneSet(page, workbenchSidebarPage, "Set B", setBGenes);

    // Select both sets
    await workbenchSidebarPage.selectSet("Set A");
    await workbenchSidebarPage.selectSet("Set B");

    // UI: Switch to union operation
    await expect(page.getByRole("button", { name: /union/i })).toBeVisible({
      timeout: 10_000,
    });
    await page.getByRole("button", { name: /union/i }).click();

    // UI: Preview count shows union size
    await workbenchSidebarPage.expectComposeResultCount(unionCount);

    // Perform union
    const createBtn = page.getByRole("button", { name: /create/i });
    await expect(createBtn).toBeEnabled();
    await createBtn.click();
    await workbenchSidebarPage.expectSetCount(3);

    // API: Derived set has correct count and operation
    const resp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const sets = await resp.json();
    const derived = sets.find((gs: { source: string }) => gs.source === "derived");
    expect(derived).toBeDefined();
    expect(derived.geneCount).toBe(unionCount);
    expect(derived.operation).toBe("union");
  });

  // ── Delete Gene Set ───────────────────────────────────────────────
  test("delete gene set removes it from sidebar and database", async ({
    page,
    seedData,
    workbenchSidebarPage,
    apiClient,
  }) => {
    const genes = seedData.plasmoGenes.slice(0, 2);
    await addGeneSet(page, workbenchSidebarPage, "To Delete", genes);
    await workbenchSidebarPage.expectSetCount(1);

    // UI: Activate the set so Delete button targets it
    await workbenchSidebarPage.activateSet("To Delete");
    // Wait for active set header to confirm the set is fully loaded
    await expect(
      page.getByRole("heading", { name: "To Delete", level: 1 }),
    ).toBeVisible();

    // UI: Click Delete button in toolbar (exact match to avoid matching "To Delete" card)
    const deleteBtn = page.getByRole("button", { name: /^Delete$/i });
    await expect(deleteBtn).toBeEnabled({ timeout: 5000 });
    await deleteBtn.click();

    // UI: Confirm deletion in the alert dialog
    const confirmBtn = page
      .getByRole("alertdialog")
      .getByRole("button", { name: /delete/i });
    await expect(confirmBtn).toBeVisible();
    await confirmBtn.click();

    // UI: Gene set is gone from sidebar
    await workbenchSidebarPage.expectSetCount(0);
    await workbenchSidebarPage.expectEmptyState();

    // API: Gene set deleted from database
    const resp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(resp.ok()).toBeTruthy();
    const sets = await resp.json();
    const deleted = sets.find((gs: { name: string }) => gs.name === "To Delete");
    expect(deleted).toBeUndefined();
  });

  // ── Panel expand / collapse ───────────────────────────────────────
  test("enrichment panel can be expanded and collapsed", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    const genes = seedData.plasmoGenes.slice(0, 3);
    await addAndActivateGeneSet(page, workbenchSidebarPage, "Panel Toggle", genes);

    // UI: Expand enrichment panel
    await workbenchMainPage.expandPanel("Enrichment Analysis");
    await workbenchMainPage.expectPanelExpanded("Enrichment Analysis");

    // UI: Collapse it back
    await workbenchMainPage.collapsePanel("Enrichment Analysis");

    // UI: Panel button visible but collapsed
    await workbenchMainPage.expectPanelVisible("Enrichment Analysis");
    // Verify it's not expanded
    await expect(
      page
        .getByRole("button", { expanded: true })
        .filter({ hasText: "Enrichment Analysis" }),
    ).not.toBeVisible();
  });

  // ── Switching active gene set ─────────────────────────────────────
  test("switching active gene set updates header and panel state", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    const genesA = seedData.plasmoGenes.slice(0, 3);
    const genesB = seedData.plasmoGenes.slice(0, 2);

    await addGeneSet(page, workbenchSidebarPage, "Set Alpha", genesA);
    await addGeneSet(page, workbenchSidebarPage, "Set Beta", genesB);

    // Activate Set Alpha
    await workbenchSidebarPage.activateSet("Set Alpha");
    await workbenchMainPage.expectActiveSetHeader("Set Alpha", genesA.length);

    // Switch to Set Beta
    await workbenchSidebarPage.activateSet("Set Beta");
    await workbenchMainPage.expectActiveSetHeader("Set Beta", genesB.length);

    // Panels still visible for new active set
    await workbenchMainPage.expectPanelVisible("Enrichment Analysis");
  });

  // ── Empty workbench state ─────────────────────────────────────────
  test("workbench shows welcome state when no gene set is active", async ({
    workbenchMainPage,
  }) => {
    await workbenchMainPage.expectEmptyState();
  });

  // ── All panels listed ──────────────────────────────────────────
  test("all analysis panels are listed when a gene set is active", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    await addAndActivateGeneSet(
      page,
      workbenchSidebarPage,
      "Panel List",
      seedData.plasmoGenes.slice(0, 3),
    );

    const panelTitles = [
      "Results Table",
      "Enrichment Analysis",
      "Distribution Explorer",
      "Gene Confidence",
      "Ensemble Scoring",
      "Reverse Search",
      "Custom Enrichment",
      "Parameter Sweep",
    ];

    for (const title of panelTitles) {
      await workbenchMainPage.expectPanelVisible(title);
    }
  });
});
