import { test, expect } from "../fixtures/test";
import { clearAllGeneSets } from "../fixtures/api-client";
import { entrySiteId } from "../fixtures/entry-site";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

test.describe("Workbench routing", () => {
  // The bare `/workbench` and `/workbench/{id}` routes redirect to the site
  // the api reports available, so a gene set has to live on that same site.
  test.beforeEach(async ({ page }) => {
    await clearAllGeneSets(page.context(), BASE_URL);
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
  });

  test("/workbench shows landing state, clicking gene set navigates to /workbench/{id}", async ({
    page,
    seedData,
    workbenchSidebarPage,
    workbenchMainPage,
  }) => {
    // Add a gene set
    await workbenchSidebarPage.openAddModal();
    await page.getByLabel(/name/i).fill("Routing Test Set");
    await page
      .getByLabel(/gene ids/i)
      .fill(seedData.plasmoGenes.slice(0, 3).join("\n"));
    await page.getByRole("button", { name: /add gene set/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 10_000 });

    // Navigate to /workbench — should show landing state (no active gene set)
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await workbenchMainPage.expectEmptyState();

    // Click the gene set in the sidebar — should navigate to /workbench/{id}
    await workbenchSidebarPage.activateSet("Routing Test Set");
    await expect(page).toHaveURL(/\/workbench\/.+/);
    await workbenchMainPage.expectActiveSetHeader("Routing Test Set", 3);
  });

  test("direct navigation to /workbench/{id} activates the gene set", async ({
    page,
    seedData,
    apiClient,
    workbenchMainPage,
  }) => {
    // Create gene set via API
    const resp = await apiClient.post(`${BASE_URL}/api/v1/gene-sets`, {
      data: {
        name: "Direct Nav Set",
        source: "paste",
        geneIds: seedData.plasmoGenes.slice(0, 2),
        siteId: await entrySiteId(page.context(), BASE_URL),
      },
    });
    expect(resp.ok()).toBeTruthy();
    const geneSet = await resp.json();

    // Navigate directly to /workbench/{id}
    await page.goto(`/workbench/${geneSet.id}`);
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await workbenchMainPage.expectActiveSetHeader("Direct Nav Set", 2);
  });

  test("navigating from /workbench/{id} back to /workbench shows landing state", async ({
    page,
    seedData,
    apiClient,
    workbenchMainPage,
  }) => {
    // Create gene set via API
    const resp = await apiClient.post(`${BASE_URL}/api/v1/gene-sets`, {
      data: {
        name: "Back Nav Set",
        source: "paste",
        geneIds: seedData.plasmoGenes.slice(0, 2),
        siteId: await entrySiteId(page.context(), BASE_URL),
      },
    });
    expect(resp.ok()).toBeTruthy();
    const geneSet = await resp.json();

    // Navigate to /workbench/{id} — gene set active
    await page.goto(`/workbench/${geneSet.id}`);
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await workbenchMainPage.expectActiveSetHeader("Back Nav Set", 2);

    // Navigate back to /workbench — should show landing state
    await page.goto("/workbench");
    await expect(page.getByRole("heading", { name: /gene sets/i })).toBeVisible();
    await workbenchMainPage.expectEmptyState();
  });
});
