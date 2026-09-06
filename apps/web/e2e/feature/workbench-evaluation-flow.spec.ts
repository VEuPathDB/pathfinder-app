import type { Page } from "@playwright/test";
import { test, expect } from "../fixtures/a11y";
import { clearAllGeneSets } from "../fixtures/api-client";
import type { WorkbenchSidebarPage } from "../pages/workbench-sidebar.page";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

async function createGeneSet(
  page: Page,
  sidebar: WorkbenchSidebarPage,
  name: string,
  geneIds: string[],
): Promise<void> {
  await sidebar.openAddModal();
  await page.getByLabel(/name/i).fill(name);
  await page.getByLabel(/gene ids/i).fill(geneIds.join("\n"));
  await page.getByRole("button", { name: /add gene set/i }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });
  await sidebar.expectSetGeneCount(name, geneIds.length);
}

/** The ensemble chip for one gene set, named by the set it toggles. */
function ensembleChip(page: Page, setName: string) {
  return page
    .getByTestId("ensemble-set-chip")
    .and(page.getByRole("button", { name: setName, exact: true }));
}

test.describe("Workbench Ensemble Scoring Flow", () => {
  test("score genes across two sets and mark a positive control", async ({
    page,
    seedData,
    sitePicker,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    await clearAllGeneSets(page.context(), BASE_URL);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");

    const genes = seedData.plasmoGenes;
    expect(genes.length).toBeGreaterThanOrEqual(5);
    const setA = genes.slice(0, 4); // [0,1,2,3]
    const setB = genes.slice(1, 5); // [1,2,3,4] — overlaps A on [1,2,3]
    const sharedGene = genes[2]; // in both sets → count 2/2
    if (sharedGene === undefined) throw new Error("seed data missing genes");

    await createGeneSet(page, workbenchSidebarPage, "Ensemble A", setA);
    await createGeneSet(page, workbenchSidebarPage, "Ensemble B", setB);

    // Activate a set so the analysis panels render, then open Ensemble Scoring.
    await workbenchSidebarPage.activateSet("Ensemble A");
    await workbenchMainPage.expandPanel("Ensemble Scoring");
    await workbenchMainPage.expectPanelExpanded("Ensemble Scoring");

    // Select both gene sets.
    await expect(page.getByTestId("ensemble-set-chip")).toHaveCount(2);
    const chipA = ensembleChip(page, "Ensemble A");
    const chipB = ensembleChip(page, "Ensemble B");
    await chipA.click();
    await chipB.click();
    await expect(chipA).toHaveAttribute("aria-pressed", "true");
    await expect(chipB).toHaveAttribute("aria-pressed", "true");

    // Add the shared gene as a positive control via the autocomplete.
    const controls = page.getByTestId("gene-chip-input");
    await controls.getByPlaceholder(/search genes/i).fill(sharedGene);
    const dropdownItem = page
      .getByTestId("gene-autocomplete-result")
      .and(page.locator(`[data-gene-id="${sharedGene}"]`));
    await expect(dropdownItem).toBeVisible({ timeout: 15_000 });
    await dropdownItem.click();

    // Compute ensemble scores (real API call).
    const computeBtn = page.getByRole("button", { name: /^compute$/i });
    await expect(computeBtn).toBeEnabled();
    await computeBtn.click();

    // The shared gene appears in both sets (2/2) and is flagged in positives.
    await expect(page.getByTestId("ensemble-results")).toBeVisible({
      timeout: 60_000,
    });
    const sharedRow = page
      .getByTestId("ensemble-row")
      .and(page.locator(`[data-gene-id="${sharedGene}"]`));
    await expect(sharedRow).toBeVisible();
    await expect(sharedRow).toContainText("2/2");
    await expect(sharedRow).toContainText(/Yes/);
  });

  test("ensemble panel is disabled with fewer than two gene sets", async ({
    page,
    seedData,
    sitePicker,
    workbenchSidebarPage,
  }) => {
    await clearAllGeneSets(page.context(), BASE_URL);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");

    await createGeneSet(
      page,
      workbenchSidebarPage,
      "Only One",
      seedData.plasmoGenes.slice(0, 4),
    );
    // Activate it so the panels render.
    await workbenchSidebarPage.activateSet("Only One");

    // Needs 2+ sets — the panel header button is disabled.
    const panelBtn = page.getByRole("button").filter({ hasText: "Ensemble Scoring" });
    await expect(panelBtn).toBeVisible();
    await expect(panelBtn).toBeDisabled();
  });

  test("compute is gated until two gene sets are selected", async ({
    page,
    seedData,
    sitePicker,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    await clearAllGeneSets(page.context(), BASE_URL);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await sitePicker.selectSite("plasmodb");

    const genes = seedData.plasmoGenes;
    await createGeneSet(page, workbenchSidebarPage, "Gate A", genes.slice(0, 4));
    await createGeneSet(page, workbenchSidebarPage, "Gate B", genes.slice(1, 5));

    await workbenchSidebarPage.activateSet("Gate A");
    await workbenchMainPage.expandPanel("Ensemble Scoring");
    await workbenchMainPage.expectPanelExpanded("Ensemble Scoring");

    const computeBtn = page.getByRole("button", { name: /^compute$/i });

    // No selection → disabled; one selection → still disabled.
    await expect(computeBtn).toBeDisabled();
    await ensembleChip(page, "Gate A").click();
    await expect(computeBtn).toBeDisabled();

    // Two selections → enabled.
    await ensembleChip(page, "Gate B").click();
    await expect(computeBtn).toBeEnabled();
  });
});
